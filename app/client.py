from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest


from app.database.requests import (
    set_user, update_user, get_card, get_card_photos, get_user, get_shop_description, get_shop_contacts
)
import app.keyboards as kb
import app.database.requests_cart as rqc
import app.database.requests_orders as rqo
from app.orders import (
    OrderStatus, ACTIVE_STATUSES, FINISHED_STATUSES, customer_order_keyboard, customer_order_text, customer_orders_list,
    customer_cancel_confirm_keyboard, manager_order_keyboard, manager_order_text,
)
from app.validation import clean_name, clean_text, normalize_phone, ADDRESS_MIN_LENGTH, ADDRESS_MAX_LENGTH


import asyncio
import logging
import math
import time
from contextlib import suppress
import os
from dotenv import load_dotenv

load_dotenv()


import ssl
import certifi
from cachetools import TTLCache
from geopy.geocoders import Nominatim


client = Router()
logger = logging.getLogger(__name__)


ORDER_COOLDOWN_SECONDS = 60

# user_id -> время последнего заказа; запись сама исчезает через ORDER_COOLDOWN_SECONDS
recent_orders: TTLCache = TTLCache(maxsize=10_000, ttl=ORDER_COOLDOWN_SECONDS)


ctx = ssl.create_default_context(cafile=certifi.where())
geolocator = Nominatim(user_agent="TelegramBotShop", ssl_context=ctx)


@client.message(CommandStart())  # Самое начало
async def cmd_start(message: Message, state: FSMContext):
    is_user = await set_user(message.from_user.id)
    if not is_user:  # если нет юзера, то добавим его в БД
        await message.answer(
            text="👋 Добро пожаловать!\nПройдите, пожалуйста, регистрацию.",
            reply_markup=await kb.clients_name(message.from_user.first_name),
        )
        await state.set_state("req_name")
    else:  # Если есть юзер
        await message.answer(
            f"🛍 {await get_shop_description()}\n\nИспользуя кнопки ниже, ознакомьтесь с ассортиментом 👇",
            reply_markup=kb.menu,
        )


@client.message(F.text == kb.BTN_CONTACTS)
async def contact(message: Message):
    await message.answer(f"📞 Контакты\n\n{await get_shop_contacts()}")


@client.message(F.text, StateFilter("req_name"))  # Имя при регистрации
async def get_req_name(message: Message, state: FSMContext):
    name = clean_name(message.text)
    if not name:
        await message.answer("❌ Имя должно состоять из букв (можно пробел и дефис), от 2 до 25 символов. Введите снова:")
        return
    await state.update_data(name=name)
    await message.answer(
        "📱 Введите ваш номер телефона или поделитесь контактом.\nПример: +79817793276",
        reply_markup=await kb.clients_phone(),
    )
    await state.set_state("req_phone")


@client.message(StateFilter("req_name"))  # Стикер, фото и т.п. вместо имени
async def get_req_name_invalid(message: Message):
    await message.answer("❌ Отправьте имя текстом:")


async def finish_registration(message: Message, state: FSMContext, phone_number: str):
    data = await state.get_data()
    await update_user(message.from_user.id, data["name"], phone_number)
    await message.answer(text="✅ Вы успешно зарегистрировались!", reply_markup=kb.menu)
    await state.clear()


@client.message(F.contact, StateFilter("req_phone"))  # Номер через «Поделиться контактом»
async def get_req_phone_contact(message: Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("❌ Поделитесь своим контактом, а не чужим:")
        return
    phone = message.contact.phone_number
    await finish_registration(message, state, normalize_phone(phone) or phone)


@client.message(F.text, StateFilter("req_phone"))  # Номер вручную
async def get_req_phone_text(message: Message, state: FSMContext):
    phone = normalize_phone(message.text)
    if not phone:
        await message.answer("❌ Некорректный номер. Введите российский номер, например +79817793276:")
        return
    await finish_registration(message, state, phone)


@client.message(StateFilter("req_phone"))
async def get_req_phone_invalid(message: Message):
    await message.answer("❌ Отправьте номер текстом или нажмите «📱 Поделиться контактом»:")


def render_cart_text(cart_items: list, total: int) -> str:
    lines = [f"• {item['name']} × {item['quantity']} = {item['total']} ₽" for item in cart_items]
    return "🛒 Ваша корзина:\n\n" + "\n".join(lines) + f"\n\n💰 Итого: {total} ₽"


async def show_cart(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и клавиатура корзины, общие для показа и обновления после кнопок"""
    cart_items, total = await rqc.get_cart_details(user_id)
    if not cart_items:
        return "🛒 Ваша корзина пуста.", kb.empty_cart
    return render_cart_text(cart_items, total), kb.get_cart_keyboard(cart_items)


@client.message(F.text == kb.BTN_CART)
async def get_cart_user(message: Message):
    text, keyboard = await show_cart(message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


async def orders_list_for(user_id: int, is_history: bool):
    statuses = FINISHED_STATUSES if is_history else ACTIVE_STATUSES
    return customer_orders_list(await rqo.get_user_orders(user_id, statuses), is_history)


@client.message(F.text == kb.BTN_ORDERS)
async def my_orders(message: Message):
    text, keyboard = await orders_list_for(message.from_user.id, is_history=False)
    await message.answer(text, reply_markup=keyboard)


@client.callback_query(F.data.in_({"myorders", "myorders_history"}))
async def my_orders_switch(callback: CallbackQuery):
    await callback.answer()
    text, keyboard = await orders_list_for(callback.from_user.id, is_history=callback.data == "myorders_history")
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard)


async def get_own_order(callback: CallbackQuery, order_id: int):
    """Заказ покупателя или None. callback_data можно подделать, поэтому владельца проверяем всегда"""
    order = await rqo.get_order(order_id)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return None
    return order


@client.callback_query(F.data.startswith("myorder_"))
async def my_order_details(callback: CallbackQuery):
    order = await get_own_order(callback, int(callback.data.split("_")[1]))
    if order is None:
        return
    await callback.answer()
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(customer_order_text(order), reply_markup=customer_order_keyboard(order))


@client.callback_query(F.data.startswith("ucancel_"))  # первый шаг отмены: просим подтвердить
async def customer_cancel_ask(callback: CallbackQuery):
    order = await get_own_order(callback, int(callback.data.split("_")[1]))
    if order is None:
        return
    if order.status != OrderStatus.NEW:
        await callback.answer("Заказ уже принят в работу, отменить его можно через менеджера: «📞 Контакты».",
                              show_alert=True)
        with suppress(TelegramBadRequest):
            await callback.message.edit_text(customer_order_text(order), reply_markup=customer_order_keyboard(order))
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=customer_cancel_confirm_keyboard(order.id))


@client.callback_query(F.data.startswith("ucancelyes_"))
async def customer_cancel_confirm(callback: CallbackQuery):
    order = await get_own_order(callback, int(callback.data.split("_")[1]))
    if order is None:
        return
    is_cancelled, order = await rqo.change_order_status(
        order.id, OrderStatus.CANCELLED, "покупателем", by_customer=True
    )
    if not is_cancelled:
        # Менеджер успел принять заказ, пока покупатель подтверждал отмену
        await callback.answer("Заказ уже принят в работу, отменить его можно через менеджера: «📞 Контакты».",
                              show_alert=True)
    else:
        await callback.answer("❌ Заказ отменён")
        await notify_managers_about_cancel(callback.bot, order)
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(customer_order_text(order), reply_markup=customer_order_keyboard(order))


async def notify_managers_about_cancel(bot, order):
    """Обновляет сообщение заказа в чате менеджеров и отдельно сообщает об отмене, чтобы её не пропустили"""
    if not order.admin_message_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=orders_chat_id(), message_id=order.admin_message_id,
            text=manager_order_text(order), reply_markup=None,
        )
        await bot.send_message(orders_chat_id(), f"❌ Покупатель отменил заказ №{order.id}",
                               reply_to_message_id=order.admin_message_id)
    except Exception:
        logger.warning("Не удалось сообщить менеджерам об отмене заказа №%s", order.id, exc_info=True)


async def refresh_cart_message(callback: CallbackQuery):
    text, keyboard = await show_cart(callback.from_user.id)
    # Двойное нажатие даёт «message is not modified», это не ошибка
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard)


@client.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery):
    card_id = int(callback.data.split("_")[-1])
    try:
        await rqc.add_to_cart(callback.from_user.id, card_id)
    except rqc.CartError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer("✅ Добавлено в корзину")


@client.callback_query(F.data.startswith("cart_inc_"))
async def cart_increase(callback: CallbackQuery):
    try:
        await rqc.change_quantity(callback.from_user.id, int(callback.data.split("_")[-1]), 1)
    except rqc.CartError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    await refresh_cart_message(callback)


@client.callback_query(F.data.startswith("cart_dec_"))
async def cart_decrease(callback: CallbackQuery):
    await rqc.change_quantity(callback.from_user.id, int(callback.data.split("_")[-1]), -1)
    await callback.answer()
    await refresh_cart_message(callback)


@client.callback_query(F.data.startswith("cart_del_"))
async def cart_remove_item(callback: CallbackQuery):
    await rqc.remove_from_cart(callback.from_user.id, int(callback.data.split("_")[-1]))
    await callback.answer("🗑 Товар удалён")
    await refresh_cart_message(callback)


@client.callback_query(F.data == "cart_clear")
async def cart_clear(callback: CallbackQuery):
    await rqc.clear_cart(callback.from_user.id)
    await callback.answer("🧹 Корзина очищена")
    await refresh_cart_message(callback)


@client.callback_query(F.data == "ignore")  # кнопки-подписи в корзине
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()


@client.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    await callback.answer()
    # Reply-клавиатуру нельзя прикрепить через edit, поэтому отправляем новое сообщение
    await callback.message.delete()
    await callback.message.answer("🏠 Главное меню", reply_markup=kb.menu)


@client.callback_query(F.data == "categories")  # это кнопка назад
@client.message(F.text == kb.BTN_CATALOG)  # это нажатие на кнопку
async def catalog(event: Message | CallbackQuery):
    if isinstance(event, Message):
        await event.answer(
            "🛍 Выберите категорию товара", reply_markup=await kb.categories()
        )
    else:
        await event.answer()
        await event.message.edit_text(
            "🛍 Выберите категорию товара", reply_markup=await kb.categories()
        )


@client.callback_query(F.data.startswith("category_"))  # category_{id} или category_{id}_{страница}
async def cards(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    category_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    keyboard = await kb.cards(category_id, page)
    if callback.message.photo:  # из карточки товара: фото нельзя превратить в текст
        await callback.message.delete()
        await callback.message.answer("📦 Выберите товар", reply_markup=keyboard)
    else:
        with suppress(TelegramBadRequest):  # повторное нажатие на ту же страницу
            await callback.message.edit_text("📦 Выберите товар", reply_markup=keyboard)


def card_caption(card) -> str:
    return f"📦 {card.name}\n\n{card.description}\n\n💰 Цена: {card.price} ₽"


@client.callback_query(F.data.startswith("card_"))  # card_{id}_{страница каталога}
async def card_info(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    card_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    card = await get_card(card_id)
    if not card:
        await callback.message.answer("😔 Этот товар больше не продаётся.")
        return
    photos = await get_card_photos(card_id)
    await callback.message.answer_photo(
        photo=photos[0],
        caption=card_caption(card),
        reply_markup=kb.card_keyboard(card.category_id, card_id, page, 0, len(photos)),
    )


@client.callback_query(F.data.startswith("photo_"))  # photo_{card_id}_{страница}_{номер фото}
async def card_photo_switch(callback: CallbackQuery):
    _, card_id, page, photo_index = callback.data.split("_")
    card_id, page, photo_index = int(card_id), int(page), int(photo_index)
    card = await get_card(card_id)
    photos = await get_card_photos(card_id)
    if not card or not photos:
        await callback.answer("😔 Этот товар больше не продаётся", show_alert=True)
        return
    photo_index %= len(photos)  # фото могли удалить, пока покупатель листал
    await callback.answer()
    with suppress(TelegramBadRequest):  # то же фото: «message is not modified»
        await callback.message.edit_media(
            InputMediaPhoto(media=photos[photo_index], caption=card_caption(card)),
            reply_markup=kb.card_keyboard(card.category_id, card_id, page, photo_index, len(photos)),
        )


def orders_chat_id() -> int:
    return int(os.getenv("GROUP_ID"))


def order_cooldown_left(user_id: int) -> int:
    """Сколько секунд осталось до следующего разрешённого заказа (0 — можно заказывать)"""
    ordered_at = recent_orders.get(user_id)
    if ordered_at is None:
        return 0
    return max(1, math.ceil(ORDER_COOLDOWN_SECONDS - (time.monotonic() - ordered_at)))


async def place_order(bot, tg_user, is_pickup: bool, address: str | None):
    """Оформляет заказ из корзины. Возвращает (текст ответа покупателю, заказ или None).

    Защита от двойного заказа в два слоя:
    1. Паузу между заказами бронируем до первого await — второй клик в этом процессе сразу получит отказ.
    2. Корзина превращается в заказ атомарно в БД — даже при гонке заказ не задвоится."""
    seconds_left = order_cooldown_left(tg_user.id)
    if seconds_left:
        return f"⏳ Вы недавно оформили заказ. Следующий можно через {seconds_left} сек.", None
    recent_orders[tg_user.id] = time.monotonic()

    order = await rqo.create_order_from_cart(tg_user, is_pickup, address)
    if order is None:
        recent_orders.pop(tg_user.id, None)
        return "🛒 Корзина пуста, добавьте товары через каталог.", None

    try:
        sent_message = await bot.send_message(
            orders_chat_id(), manager_order_text(order), reply_markup=manager_order_keyboard(order)
        )
    except Exception:
        # Заказ не дошёл до менеджеров: удаляем его и возвращаем товары в корзину, чтобы покупатель мог повторить
        logger.exception("Не удалось отправить заказ №%s в чат заказов", order.id)
        await rqo.cancel_unsent_order(order)
        recent_orders.pop(tg_user.id, None)
        return "❌ Не удалось оформить заказ, попробуйте ещё раз чуть позже.", None

    await rqo.set_admin_message_id(order.id, sent_message.message_id)
    logger.info("Заказ №%s от пользователя %s на сумму %s ₽ (%s)", order.id, tg_user.id, order.total,
                "самовывоз" if is_pickup else "доставка")
    return (f"✅ Спасибо! Заказ №{order.id} оформлен.\n"
            f"Мы пришлём сообщение, когда статус заказа изменится."), order


async def finish_order(message: Message, state: FSMContext, tg_user, is_pickup: bool, address: str | None = None):
    result_text, order = await place_order(message.bot, tg_user, is_pickup, address)
    await message.answer(result_text, reply_markup=kb.menu)  # возвращаем главное меню вместо клавиатуры геопозиции
    if order:
        # Отдельным сообщением: к одному сообщению нельзя прикрепить и меню, и inline-кнопку отмены
        await message.answer(customer_order_text(order), reply_markup=customer_order_keyboard(order))
    await state.clear()
async def check_can_order(callback: CallbackQuery) -> bool:
    """Ранняя проверка перед вопросами о доставке, чтобы не спрашивать адрес зря"""
    seconds_left = order_cooldown_left(callback.from_user.id)
    if seconds_left:
        await callback.answer(
            f"⏳ Вы недавно оформили заказ. Следующий можно через {seconds_left} сек.", show_alert=True
        )
        return False
    cart_items, _ = await rqc.get_cart_details(callback.from_user.id)
    if not cart_items:
        await callback.answer("🛒 Корзина пуста", show_alert=True)
        return False
    await callback.answer()
    return True


async def ask_delivery_type(callback: CallbackQuery):
    await callback.message.answer(
        "🚚 Как вы хотите получить заказ?", reply_markup=kb.delivery_choice
    )


@client.callback_query(F.data.startswith("buy_"))  # «Купить сейчас» = в корзину + оформление
async def client_buy_callback(callback: CallbackQuery):
    try:
        await rqc.add_to_cart(callback.from_user.id, int(callback.data.split("_")[1]))
    except rqc.CartError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if await check_can_order(callback):
        await ask_delivery_type(callback)


@client.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery):
    if await check_can_order(callback):
        await ask_delivery_type(callback)


@client.callback_query(F.data == "order_pickup")
async def order_pickup(callback: CallbackQuery, state: FSMContext):
    if await check_can_order(callback):
        await finish_order(callback.message, state, callback.from_user, is_pickup=True)


@client.callback_query(F.data == "order_delivery")
async def order_delivery(callback: CallbackQuery, state: FSMContext):
    if not await check_can_order(callback):
        return
    await state.set_state("waiting_for_address")
    await callback.message.answer(
        "📍 Отправьте ваш адрес доставки.\nПример: г. Санкт-Петербург, ул. Колотушкина д.12, к/лит, кв. 1",
        reply_markup=await kb.clients_location(),
    )


@client.message(
    F.location, StateFilter("waiting_for_address")
)  # Получение адреса по геолокации и обработка заказа
async def getting_location(message: Message, state: FSMContext):
    coordinates = f"{message.location.latitude}, {message.location.longitude}"
    try:
        # geopy синхронный, поэтому выносим запрос в поток, чтобы не блокировать бота
        address = await asyncio.to_thread(
            geolocator.reverse, coordinates, exactly_one=True, language="ru", timeout=10
        )
    except Exception:
        # Сервис геокодинга недоступен или ограничил запросы: заказ не теряем, отдаём координаты
        logger.warning("Не удалось определить адрес по координатам %s", coordinates, exc_info=True)
        address = None
    address_text = str(address) if address else f"координаты {coordinates}"
    await finish_order(message, state, message.from_user, is_pickup=False, address=address_text)


@client.message(
    F.text, StateFilter("waiting_for_address")
)  # Получение адреса вручную и обработка заказа
async def getting_address_manually(message: Message, state: FSMContext):
    address = clean_text(message.text, ADDRESS_MAX_LENGTH, ADDRESS_MIN_LENGTH)
    if not address:
        await message.answer(
            f"❌ Адрес должен быть от {ADDRESS_MIN_LENGTH} до {ADDRESS_MAX_LENGTH} символов. Введите снова:"
        )
        return
    await finish_order(message, state, message.from_user, is_pickup=False, address=address)


@client.message(StateFilter("waiting_for_address"))  # Стикер, фото и т.п. вместо адреса
async def getting_address_invalid(message: Message):
    await message.answer("📍 Отправьте адрес текстом или нажмите «📍 Отправить геопозицию»:")
