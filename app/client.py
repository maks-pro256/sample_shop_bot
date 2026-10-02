from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest


from app.database.requests import (
    set_user, update_user, get_card, get_user, get_shop_description, get_shop_contacts
)
import app.keyboards as kb
import app.database.requests_cart as rqc
from app.validation import clean_name, clean_text, normalize_phone, ADDRESS_MIN_LENGTH, ADDRESS_MAX_LENGTH
from app.timezone import now_msk


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


PICKUP_TEXT = "Самовывоз"
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


@client.callback_query(F.data.startswith("category_"))
async def cards(callback: CallbackQuery):
    await callback.answer()
    category_id = int(callback.data.split("_")[1])
    keyboard = await kb.cards(category_id)
    if callback.message.photo:  # из карточки товара: фото нельзя превратить в текст
        await callback.message.delete()
        await callback.message.answer("📦 Выберите товар", reply_markup=keyboard)
    else:
        await callback.message.edit_text("📦 Выберите товар", reply_markup=keyboard)


@client.callback_query(F.data.startswith("card_"))
async def card_info(callback: CallbackQuery):
    await callback.answer()
    card_id = int(callback.data.split("_")[1])
    card = await get_card(card_id)
    if not card:
        await callback.message.answer("😔 Этот товар больше не продаётся.")
        return
    await callback.message.answer_photo(
        photo=card.image,
        caption=f"📦 {card.name}\n\n{card.description}\n\n💰 Цена: {card.price} ₽",
        reply_markup=await kb.back_to_categories(card.category_id, card_id),
    )


def order_cooldown_left(user_id: int) -> int:
    """Сколько секунд осталось до следующего разрешённого заказа (0 — можно заказывать)"""
    ordered_at = recent_orders.get(user_id)
    if ordered_at is None:
        return 0
    return max(1, math.ceil(ORDER_COOLDOWN_SECONDS - (time.monotonic() - ordered_at)))


async def send_order_to_admin_chat(bot, tg_user, delivery_info: str) -> str:
    """Оформляет заказ из корзины и возвращает текст ответа покупателю.

    Защита от двойного заказа в два слоя:
    1. Паузу между заказами бронируем до первого await — второй клик в этом процессе сразу получит отказ.
    2. Корзину забираем атомарно в БД (take_cart_items) — даже при гонке заказ не задвоится."""
    seconds_left = order_cooldown_left(tg_user.id)
    if seconds_left:
        return f"⏳ Вы недавно оформили заказ. Следующий можно через {seconds_left} сек."
    recent_orders[tg_user.id] = time.monotonic()

    cart_items, total = await rqc.take_cart_items(tg_user.id)
    if not cart_items:
        recent_orders.pop(tg_user.id, None)
        return "🛒 Корзина пуста, добавьте товары через каталог."

    user = await get_user(tg_user.id)
    items_text = "\n".join(
        f"• {item['name']} (ID {item['id']}) × {item['quantity']} = {item['total']} ₽"
        for item in cart_items
    )
    username = f"@{tg_user.username}" if tg_user.username else "без username"
    delivery_icon = "🏬" if delivery_info == PICKUP_TEXT else "🚚"
    info = (
        f"🆕 Новый заказ\n"
        f"🕒 {now_msk():%d.%m.%Y %H:%M} (МСК)\n\n"
        f"👤 {user.name}, {username} (ID: {user.tg_id})\n"
        f"📞 {user.phone_number}\n"
        f"{delivery_icon} {delivery_info}\n\n"
        f"📦 Состав заказа:\n{items_text}\n\n"
        f"💰 Итого: {total} ₽"
    )
    try:
        await bot.send_message(int(os.getenv("GROUP_ID")), info)
    except Exception:
        # Заказ не дошёл до админов: возвращаем товары в корзину, чтобы покупатель мог повторить
        logger.exception("Не удалось отправить заказ пользователя %s в чат заказов", tg_user.id)
        await rqc.restore_cart_items(tg_user.id, cart_items)
        recent_orders.pop(tg_user.id, None)
        return "❌ Не удалось оформить заказ, попробуйте ещё раз чуть позже."

    logger.info("Заказ от пользователя %s на сумму %s ₽ (%s)", tg_user.id, total, delivery_info.split(",")[0])
    return "✅ Спасибо, ваш заказ принят! Скоро с вами свяжется менеджер."


async def finish_order(message: Message, state: FSMContext, tg_user, delivery_info: str):
    result_text = await send_order_to_admin_chat(message.bot, tg_user, delivery_info)
    await message.answer(result_text, reply_markup=kb.menu)
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
        await finish_order(callback.message, state, callback.from_user, PICKUP_TEXT)


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
    await finish_order(message, state, message.from_user, f"Доставка, адрес: {address_text}")


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
    await finish_order(message, state, message.from_user, f"Доставка, адрес: {address}")


@client.message(StateFilter("waiting_for_address"))  # Стикер, фото и т.п. вместо адреса
async def getting_address_invalid(message: Message):
    await message.answer("📍 Отправьте адрес текстом или нажмите «📍 Отправить геопозицию»:")
