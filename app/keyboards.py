from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup


from app.database.requests import get_categories, get_cards_by_category


class AddCategory(StatesGroup):
    waiting_for_title = State()


class EditShopDescription(StatesGroup):
    waiting_for_text = State()


class AddCard(StatesGroup):
    category = State()
    name = State()
    price = State()
    description = State()
    photo = State()


menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text='Каталог')],
    [KeyboardButton(text='Контакты')],
    [KeyboardButton(text="Корзина")]
],
    resize_keyboard=True,
    input_field_placeholder='Выберите пункт меню...')


def get_product_keyboard_with_cart(card_id: int):
    """Клавиатура товара с кнопкой корзины"""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить в корзину", callback_data=f"add_to_cart_{card_id}")
    builder.button(text="🔙 Назад", callback_data="back_to_cards")
    builder.adjust(1)
    return builder.as_markup()

def get_cart_keyboard(cart_items: list):
    """Клавиатура корзины"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки для изменения количества
    for item in cart_items:
        builder.row(
            InlineKeyboardButton(
                text=f"{item['name']} - {item['quantity']} шт | {item['total']}₽",
                callback_data=f"cart_item_{item['id']}"
            )
        )
        builder.row(
            InlineKeyboardButton(text="➖", callback_data=f"cart_dec_{item['id']}"),
            InlineKeyboardButton(text=f"{item['quantity']} шт", callback_data="ignore"),
            InlineKeyboardButton(text="➕", callback_data=f"cart_inc_{item['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"cart_del_{item['id']}")
        )
    
    builder.row(
        InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout"),
        InlineKeyboardButton(text="🔄 Очистить всё", callback_data="cart_clear")
    )
    builder.row(
        InlineKeyboardButton(text="🛍 Продолжить покупки", callback_data="categories"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    return builder.as_markup()


inline_admin_panel = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Добавить что-то", callback_data='add_product')], 
        [InlineKeyboardButton(text="Удалить что-то", callback_data="remove_product")],
        [InlineKeyboardButton(text="Изменить описание магазина", callback_data="edit_shop_description")]]
)


delivery_choice = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Доставка", callback_data="order_delivery")],
        [InlineKeyboardButton(text="🏬 Самовывоз", callback_data="order_pickup")]
    ]
)


panel_add = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Добавить категорию", callback_data="add_category")],
        [InlineKeyboardButton(text="Добавить карточку товара", callback_data="add_card")]
    ]
)


panel_del = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Удалить категорию", callback_data="del_category")],
        [InlineKeyboardButton(text="Удалить карточку товара", callback_data="del_card")]
    ]
)


async def clients_name(name):
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=name)]],
                               resize_keyboard=True,
                               input_field_placeholder='Введите имя или оставьте такое же')


async def clients_phone():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text='Поделиться контактом',
                        request_contact=True)]
    ],
        resize_keyboard=True,
        input_field_placeholder='Введите номер или поделитесь контактом')


async def clients_location():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Отправить свою текущую геопозицию',
                                                         request_location=True)]],
                                resize_keyboard=True,
                                input_field_placeholder='Введите адрес или отправьте геолокацию')


async def categories():
    Keyboard = InlineKeyboardBuilder()
    all_categories = await get_categories()
    for category in all_categories:
        Keyboard.add(InlineKeyboardButton(text=category.name,
                                          callback_data=f'category_{category.id}'))
    return Keyboard.adjust(2).as_markup()


async def categories_admin():
    Keyboard = InlineKeyboardBuilder()
    all_categories = await get_categories()
    for category in all_categories:
        Keyboard.add(InlineKeyboardButton(text=category.name,
                                          callback_data=f'categoryes_{category.id}'))
    return Keyboard.adjust(2).as_markup()


async def categories_admin_del():
    Keyboard = InlineKeyboardBuilder()
    all_categories = await get_categories()
    for category in all_categories:
        Keyboard.add(InlineKeyboardButton(text=category.name,
                                          callback_data=f'cat_{category.id}'))
    return Keyboard.adjust(2).as_markup()


async def categories_admin_2del():
    Keyboard = InlineKeyboardBuilder()
    all_categories = await get_categories()
    for category in all_categories:
        Keyboard.add(InlineKeyboardButton(text=category.name,
                                          callback_data=f'cate_{category.id}'))
    return Keyboard.adjust(2).as_markup()


async def cards(category_id: int):
    keyboard = InlineKeyboardBuilder()
    all_cards = await get_cards_by_category(category_id)
    for card in all_cards:
        keyboard.row(InlineKeyboardButton(text=f'{card.name} | {card.price}RUB',
                                          callback_data=f'card_{card.id}'))
    keyboard.row(InlineKeyboardButton(
        text='Назад', callback_data='categories'))
    return keyboard.as_markup()


async def cards_admin(category_id: int):
    keyboard = InlineKeyboardBuilder()
    all_cards = await get_cards_by_category(category_id)
    for card in all_cards:
        keyboard.row(InlineKeyboardButton(text=f'{card.name} | {card.price}RUB',
                                          callback_data=f'carda_{card.id}'))
    keyboard.row(InlineKeyboardButton(
        text='Назад', callback_data='categories'))
    return keyboard.as_markup()


async def back_to_categories(category_id: int, card_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Купить', callback_data=f'buy_{card_id}')],
        [InlineKeyboardButton(
            text='Назад', callback_data=f'category_{category_id}')]
    ])

