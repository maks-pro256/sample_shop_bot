from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext


from app.database.requests import set_user, update_user, get_card, get_user, get_shop_description
import app.keyboards as kb
import app.database.requests_cart as rqc
from app.validation import validation_phone


import os
from dotenv import load_dotenv

load_dotenv()


import ssl
import certifi
from geopy.geocoders import Nominatim


client = Router()


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


@client.message(F.text == "Корзина")
async def get_cart_user(message: Message):
    card_id = await rqc.get_or_create_cart(message.from_user.id)
    await message.answer("Добро пожаловать в корзину!", 
                         reply_markup=await kb.get_product_keyboard_with_cart(card_id))


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
    category_name = callback.data.split("_")[1]
    try:
        await callback.message.edit_text(
            "Выберите товар", reply_markup=await kb.cards(category_name)
        )
    except:
        await callback.message.delete()
        await callback.message.edit_text(
            "Выберите товар", reply_markup=await kb.cards(category_name)
        )


@client.callback_query(F.data.startswith("card_"))
async def card_info(callback: CallbackQuery):
    await callback.answer()
    card_id = callback.data.split("_")[1]
    card = await get_card(card_id)
    await callback.message.answer_photo(
        photo=card.image,
        caption=f"{card.name}\n\n{card.description}\n\n{card.price}RUB",
        reply_markup=await kb.back_to_categories(card.category_name, card_id),
    )


async def send_order_to_admin_chat(bot, tg_user, card_id, delivery_info: str):
    """Собирает заказ и отправляет его в чат, указанный в GROUP_ID"""
    user = await get_user(tg_user.id)
    info = (
        f"Новый заказ:\n\n"
        f"Пользователь: {user.name}, @{tg_user.username} (ID: {user.tg_id})\n"
        f"Номер телефона: {user.phone_number}\n"
        f"Получение: {delivery_info}\n"
        f"ID товара: {card_id}"
    )
    await bot.send_message(int(os.getenv("GROUP_ID")), info)


@client.callback_query(F.data.startswith("buy_"))
async def client_buy_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    card_id = callback.data.split("_")[1]
    await state.update_data(card_id=card_id)
    await callback.message.answer(
        "Как вы хотите получить заказ?", reply_markup=kb.delivery_choice
    )


@client.callback_query(F.data == "order_pickup")
async def order_pickup(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    card_id = (await state.get_data()).get("card_id")
    if not card_id:  # кнопка из старого сообщения, товар уже неизвестен
        await callback.message.answer("Выберите товар заново через каталог.")
        return
    await send_order_to_admin_chat(
        callback.bot, callback.from_user, card_id, "Самовывоз"
    )
    await callback.message.answer("Спасибо, ваш заказ принят!", reply_markup=kb.menu)
    await state.clear()


@client.callback_query(F.data == "order_delivery")
async def order_delivery(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not (await state.get_data()).get("card_id"):
        await callback.message.answer("Выберите товар заново через каталог.")
        return
    await state.set_state("waiting_for_address")
    await callback.message.answer(
        "Отправьте ваш адрес доставки.\nПример: г. Санкт-Петербург, ул. Колотушкина д.12, к/лит, кв. 1",
        reply_markup=await kb.clients_location(),
    )


@client.message(
    F.location, StateFilter("waiting_for_address")
)  # Получение адреса  и обработка заказа
async def getting_location(message: Message, state: FSMContext):
    data = await state.get_data()
    address = geolocator.reverse(
        f"{message.location.latitude}, {message.location.longitude}",
        exactly_one=True,
        language="ru",
    )
    await send_order_to_admin_chat(
        message.bot, message.from_user, data.get("card_id"), f"Доставка, адрес: {address}"
    )
    await message.answer("Спасибо, ваш заказ принят!", reply_markup=kb.menu)
    await state.clear()


@client.message(
    StateFilter("waiting_for_address")
)  # Получение адреса вручную и обработка заказа
async def getting_address_manually(message: Message, state: FSMContext):
    data = await state.get_data()
    await send_order_to_admin_chat(
        message.bot, message.from_user, data.get("card_id"), f"Доставка, адрес: {message.text}"
    )
    await message.answer("Спасибо, ваш заказ принят!", reply_markup=kb.menu)
    await state.clear()
