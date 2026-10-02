from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest


from app.database.requests import set_user, update_user, get_card, get_user, get_shop_description
import app.keyboards as kb
import app.database.requests_cart as rqc
from app.validation import validation_phone


import asyncio
import logging
from contextlib import suppress
import os
from dotenv import load_dotenv

load_dotenv()


import ssl
import certifi
from geopy.geocoders import Nominatim


client = Router()
logger = logging.getLogger(__name__)


ctx = ssl.create_default_context(cafile=certifi.where())
geolocator = Nominatim(user_agent="TelegramBotShop", ssl_context=ctx)


@client.message(CommandStart())  # Самое начало
async def cmd_start(message: Message, state: FSMContext):
    is_user = await set_user(message.from_user.id)
    if not is_user:  # если нет юзера, то добавим его в БД
        await message.answer(
            text="Добро пожаловать! \nПройдите процесс регистрации...",
            reply_markup=await kb.clients_name(message.from_user.first_name),
        )
        await state.set_state("req_name")
    else:  # Если есть юзер
        await message.answer(
            f"{await get_shop_description()}\n\nИспользуя кнопки ниже, ознакомьтесь с ассортиментом",
            reply_markup=kb.menu,
        )


@client.message(F.text == "Контакты")
async def contact(message: Message):
    text_contact = (
        f"Связывайтесь с менеджером в любом формате и в любое для вас время:\n"
        f"Номер телефона: +7981245678\n"
        f"Телеграмм: @manaka2"
    )
    await message.answer(text=text_contact)


@client.message(StateFilter("req_name"))  # Рег имени и создания состояние номера
async def qet_req_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.capitalize())
    await message.answer(
        "Введите ваш номер телефона без пробелов и скобок!\nПример: +79817793276",
        reply_markup=await kb.clients_phone(),
    )
    await state.set_state("req_phone")


@client.message(F.contact, StateFilter("req_phone"))  # Регистрация номера
async def qet_req_phone_numbers(message: Message, state: FSMContext):
    await state.update_data(phone_number=message.contact.phone_number)
    data = await state.get_data()
    await update_user(message.from_user.id, data["name"], data["phone_number"])
    await message.answer(text="Вы успешно зарегестрировались!", reply_markup=kb.menu)
    await state.clear()


@client.message(
    StateFilter("req_phone")
)  # Регистрация номера без "поделиться контактом"
async def qet_req_phone_number(message: Message, state: FSMContext):
    await state.update_data(phone_number=message.text)
    data = await state.get_data()
    if await validation_phone(data["phone_number"]):  # Валидация номера телефона успех
        await update_user(message.from_user.id, data["name"], data["phone_number"])
        await message.answer(
            text="Вы успешно зарегестрировались!", reply_markup=kb.menu
        )
        await state.clear()
    else:  # провал валидации, открываем заново регистрацию
        await state.clear()
        await message.answer(
            text="Некоректно введен номер телефона, пройдите регистрацию еще раз!",
            reply_markup=await kb.clients_name(message.from_user.first_name),
        )
        await state.set_state("req_name")


def render_cart_text(cart_items: list, total: int) -> str:
    lines = [f"• {item['name']} × {item['quantity']} = {item['total']} RUB" for item in cart_items]
    return "🛒 Ваша корзина:\n\n" + "\n".join(lines) + f"\n\nИтого: {total} RUB"


async def show_cart(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и клавиатура корзины, общие для показа и обновления после кнопок"""
    cart_items, total = await rqc.get_cart_details(user_id)
    if not cart_items:
        return "Ваша корзина пуста.", kb.empty_cart
    return render_cart_text(cart_items, total), kb.get_cart_keyboard(cart_items)


@client.message(F.text == "Корзина")
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
    await rqc.add_to_cart(callback.from_user.id, card_id)
    await callback.answer("✅ Добавлено в корзину")


@client.callback_query(F.data.startswith("cart_inc_"))
async def cart_increase(callback: CallbackQuery):
    await rqc.change_quantity(callback.from_user.id, int(callback.data.split("_")[-1]), 1)
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
    await callback.answer("Товар удалён")
    await refresh_cart_message(callback)


@client.callback_query(F.data == "cart_clear")
async def cart_clear(callback: CallbackQuery):
    await rqc.clear_cart(callback.from_user.id)
    await callback.answer("Корзина очищена")
    await refresh_cart_message(callback)


@client.callback_query(F.data == "ignore")  # кнопки-подписи в корзине
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()


@client.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    await callback.answer()
    # Reply-клавиатуру нельзя прикрепить через edit, поэтому отправляем новое сообщение
    await callback.message.delete()
    await callback.message.answer("Главное меню", reply_markup=kb.menu)


@client.callback_query(F.data == "categories")  # это кнопка назад
@client.message(F.text == "Каталог")  # это нажатие на кнопку
async def catalog(event: Message | CallbackQuery):
    if isinstance(event, Message):
        await event.answer(
            "Выберите категорию товара", reply_markup=await kb.categories()
        )
    else:
        await event.answer("Вы вурнулись назад")
        await event.message.edit_text(
            "Выберите категорию товаров", reply_markup=await kb.categories()
        )


@client.callback_query(F.data.startswith("category_"))
async def cards(callback: CallbackQuery):
    await callback.answer()
    category_id = int(callback.data.split("_")[1])
    keyboard = await kb.cards(category_id)
    if callback.message.photo:  # из карточки товара: фото нельзя превратить в текст
        await callback.message.delete()
        await callback.message.answer("Выберите товар", reply_markup=keyboard)
    else:
        await callback.message.edit_text("Выберите товар", reply_markup=keyboard)


@client.callback_query(F.data.startswith("card_"))
async def card_info(callback: CallbackQuery):
    await callback.answer()
    card_id = int(callback.data.split("_")[1])
    card = await get_card(card_id)
    if not card:
        await callback.message.answer("Этот товар больше не продаётся.")
        return
    await callback.message.answer_photo(
        photo=card.image,
        caption=f"{card.name}\n\n{card.description}\n\n{card.price}RUB",
        reply_markup=await kb.back_to_categories(card.category_id, card_id),
    )


async def send_order_to_admin_chat(bot, tg_user, delivery_info: str) -> bool:
    """Отправляет содержимое корзины в чат GROUP_ID и очищает корзину.
    Возвращает False, если корзина уже пуста (например, нажали кнопку из старого сообщения)"""
    cart_items, total = await rqc.get_cart_details(tg_user.id)
    if not cart_items:
        return False

    user = await get_user(tg_user.id)
    items_text = "\n".join(
        f"• {item['name']} (ID {item['id']}) × {item['quantity']} = {item['total']} RUB"
        for item in cart_items
    )
    info = (
        f"Новый заказ:\n\n"
        f"Пользователь: {user.name}, @{tg_user.username} (ID: {user.tg_id})\n"
        f"Номер телефона: {user.phone_number}\n"
        f"Получение: {delivery_info}\n\n"
        f"Состав заказа:\n{items_text}\n\n"
        f"Итого: {total} RUB"
    )
    await bot.send_message(int(os.getenv("GROUP_ID")), info)
    await rqc.clear_cart(tg_user.id)
    logger.info("Заказ от пользователя %s на сумму %s RUB (%s)", tg_user.id, total, delivery_info.split(",")[0])
    return True


async def finish_order(message: Message, state: FSMContext, tg_user, delivery_info: str):
    is_sent = await send_order_to_admin_chat(message.bot, tg_user, delivery_info)
    if is_sent:
        await message.answer("Спасибо, ваш заказ принят!", reply_markup=kb.menu)
    else:
        await message.answer("Корзина пуста, добавьте товары через каталог.", reply_markup=kb.menu)
    await state.clear()


async def ask_delivery_type(callback: CallbackQuery):
    await callback.message.answer(
        "Как вы хотите получить заказ?", reply_markup=kb.delivery_choice
    )


@client.callback_query(F.data.startswith("buy_"))  # «Купить сейчас» = в корзину + оформление
async def client_buy_callback(callback: CallbackQuery):
    await callback.answer()
    await rqc.add_to_cart(callback.from_user.id, int(callback.data.split("_")[1]))
    await ask_delivery_type(callback)


@client.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery):
    cart_items, _ = await rqc.get_cart_details(callback.from_user.id)
    if not cart_items:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    await callback.answer()
    await ask_delivery_type(callback)


@client.callback_query(F.data == "order_pickup")
async def order_pickup(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await finish_order(callback.message, state, callback.from_user, "Самовывоз")


@client.callback_query(F.data == "order_delivery")
async def order_delivery(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state("waiting_for_address")
    await callback.message.answer(
        "Отправьте ваш адрес доставки.\nПример: г. Санкт-Петербург, ул. Колотушкина д.12, к/лит, кв. 1",
        reply_markup=await kb.clients_location(),
    )


@client.message(
    F.location, StateFilter("waiting_for_address")
)  # Получение адреса по геолокации и обработка заказа
async def getting_location(message: Message, state: FSMContext):
    # geopy синхронный, поэтому выносим запрос в поток, чтобы не блокировать бота
    address = await asyncio.to_thread(
        geolocator.reverse,
        f"{message.location.latitude}, {message.location.longitude}",
        exactly_one=True,
        language="ru",
    )
    await finish_order(message, state, message.from_user, f"Доставка, адрес: {address}")


@client.message(
    F.text, StateFilter("waiting_for_address")
)  # Получение адреса вручную и обработка заказа
async def getting_address_manually(message: Message, state: FSMContext):
    await finish_order(message, state, message.from_user, f"Доставка, адрес: {message.text}")
