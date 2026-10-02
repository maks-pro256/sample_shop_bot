from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup


from app.database.requests import get_categories, get_cards_page


CARDS_PAGE_SIZE = 8


class AddCategory(StatesGroup):
    waiting_for_title = State()


class EditShopDescription(StatesGroup):
    waiting_for_text = State()


class EditShopContacts(StatesGroup):
    waiting_for_text = State()


class AddCard(StatesGroup):
    category = State()
    name = State()
    price = State()
    description = State()
    photo = State()


class EditCard(StatesGroup):
    value = State()   # новое название, цена или описание
    photos = State()  # новый набор фото


# Тексты кнопок главного меню: хендлеры в client.py ловят сообщения по этим же константам
BTN_CATALOG = "🛍 Каталог"
BTN_CONTACTS = "📞 Контакты"
BTN_CART = "🛒 Корзина"
BTN_ORDERS = "📦 Мои заказы"


menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text=BTN_CATALOG)],
    [KeyboardButton(text=BTN_CART), KeyboardButton(text=BTN_ORDERS)],
    [KeyboardButton(text=BTN_CONTACTS)]
],
    resize_keyboard=True,
    input_field_placeholder='Выберите пункт меню...')


def get_cart_keyboard(cart_items: list):
    """Клавиатура корзины"""
    builder = InlineKeyboardBuilder()

    for item in cart_items:
        builder.row(
            InlineKeyboardButton(
                text=f"{item['name']} | {item['total']} ₽",
                callback_data="ignore"
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


empty_cart = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="🛍 Перейти в каталог", callback_data="categories")]]
)


inline_admin_panel = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data='add_product')],
        [InlineKeyboardButton(text="✏️ Изменить товар", callback_data="edit_card")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="remove_product")],
        [InlineKeyboardButton(text="📝 Изменить описание магазина", callback_data="edit_shop_description")],
        [InlineKeyboardButton(text="📞 Изменить контакты", callback_data="edit_shop_contacts")]]
)


delivery_choice = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Доставка", callback_data="order_delivery")],
        [InlineKeyboardButton(text="🏬 Самовывоз", callback_data="order_pickup")]
    ]
)


panel_add = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📁 Добавить категорию", callback_data="add_category")],
        [InlineKeyboardButton(text="📦 Добавить карточку товара", callback_data="add_card")]
    ]
)


panel_del = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить категорию", callback_data="del_category")],
        [InlineKeyboardButton(text="🗑 Удалить карточку товара", callback_data="del_card")]
    ]
)


async def clients_name(name):
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=name)]],
                               resize_keyboard=True,
                               input_field_placeholder='Введите имя или оставьте такое же')


async def clients_phone():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text='📱 Поделиться контактом',
                        request_contact=True)]
    ],
        resize_keyboard=True,
        input_field_placeholder='Введите номер или поделитесь контактом')


async def clients_location():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='📍 Отправить геопозицию',
                                                         request_location=True)]],
                                resize_keyboard=True,
                                input_field_placeholder='Введите адрес или отправьте геолокацию')


async def categories_with_prefix(prefix: str):
    """Список категорий, у каждой кнопки callback_data = f"{prefix}_{id}" """
    keyboard = InlineKeyboardBuilder()
    for category in await get_categories():
        keyboard.add(InlineKeyboardButton(text=category.name,
                                          callback_data=f'{prefix}_{category.id}'))
    return keyboard.adjust(2).as_markup()


async def categories():
    return await categories_with_prefix('category')


async def categories_admin():
    return await categories_with_prefix('categoryes')


async def categories_admin_del():
    return await categories_with_prefix('cat')


async def categories_admin_2del():
    return await categories_with_prefix('cate')


async def categories_admin_edit():
    return await categories_with_prefix('ecat')


async def cards_page_keyboard(category_id: int, page: int, item_prefix: str,
                              page_prefix: str, back_callback: str):
    """Товары категории постранично.
    Кнопка товара: f"{item_prefix}_{card_id}_{page}" (страница нужна, чтобы «Назад» вернул на неё же).
    Листание: f"{page_prefix}_{category_id}_{page}"."""
    cards_on_page, pages_count, page = await get_cards_page(category_id, page, CARDS_PAGE_SIZE)
    keyboard = InlineKeyboardBuilder()
    for card in cards_on_page:
        keyboard.row(InlineKeyboardButton(text=f'{card.name} | {card.price} ₽',
                                          callback_data=f'{item_prefix}_{card.id}_{page}'))
    if pages_count > 1:
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton(
                text='◀️', callback_data=f'{page_prefix}_{category_id}_{page - 1}'))
        navigation.append(InlineKeyboardButton(text=f'{page + 1}/{pages_count}', callback_data='ignore'))
        if page < pages_count - 1:
            navigation.append(InlineKeyboardButton(
                text='▶️', callback_data=f'{page_prefix}_{category_id}_{page + 1}'))
        keyboard.row(*navigation)
    keyboard.row(InlineKeyboardButton(text='🔙 Назад', callback_data=back_callback))
    return keyboard.as_markup()


async def cards(category_id: int, page: int = 0):
    return await cards_page_keyboard(category_id, page, 'card', 'category', 'categories')


async def cards_admin(category_id: int, page: int = 0):
    return await cards_page_keyboard(category_id, page, 'carda', 'cat', 'remove_product')


async def cards_admin_edit(category_id: int, page: int = 0):
    return await cards_page_keyboard(category_id, page, 'ecard', 'ecat', 'edit_card')


def card_keyboard(category_id: int, card_id: int, page: int, photo_index: int, photos_count: int):
    """Карточка товара: листание фото (если их несколько), покупка и возврат на ту же страницу каталога"""
    keyboard = InlineKeyboardBuilder()
    if photos_count > 1:
        previous_index = (photo_index - 1) % photos_count
        next_index = (photo_index + 1) % photos_count
        keyboard.row(
            InlineKeyboardButton(text='◀️', callback_data=f'photo_{card_id}_{page}_{previous_index}'),
            InlineKeyboardButton(text=f'🖼 {photo_index + 1}/{photos_count}', callback_data='ignore'),
            InlineKeyboardButton(text='▶️', callback_data=f'photo_{card_id}_{page}_{next_index}'),
        )
    keyboard.row(InlineKeyboardButton(text='🛒 В корзину', callback_data=f'add_to_cart_{card_id}'))
    keyboard.row(InlineKeyboardButton(text='⚡ Купить сейчас', callback_data=f'buy_{card_id}'))
    keyboard.row(InlineKeyboardButton(text='🔙 Назад', callback_data=f'category_{category_id}_{page}'))
    return keyboard.as_markup()


photos_done = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="✅ Готово", callback_data="photos_done")]]
)


def card_edit_menu(card_id: int, category_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"efield_name_{card_id}"),
         InlineKeyboardButton(text="💰 Цена", callback_data=f"efield_price_{card_id}")],
        [InlineKeyboardButton(text="📝 Описание", callback_data=f"efield_description_{card_id}"),
         InlineKeyboardButton(text="🖼 Фото", callback_data=f"efield_photos_{card_id}")],
        [InlineKeyboardButton(text="🔙 К списку товаров", callback_data=f"ecat_{category_id}")],
    ])
