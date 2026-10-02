from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest


from sqlalchemy.exc import IntegrityError, SQLAlchemyError


import app.keyboards as kb
from app.filters import IsAdmin
import app.database.requests_admin as rq
from app.database.requests import get_shop_description, get_shop_contacts, get_card, get_card_photos
from app.validation import (
    clean_text, parse_price, CATEGORY_NAME_MAX_LENGTH, CARD_NAME_MAX_LENGTH,
    CARD_DESCRIPTION_MAX_LENGTH, MAX_PRICE, MAX_CARD_PHOTOS
)
import logging
from contextlib import suppress


admin = Router()
admin.message.filter(IsAdmin())
admin.callback_query.filter(IsAdmin())


logger = logging.getLogger(__name__)


@admin.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    await state.clear()  # /admin прерывает любой незаконченный сценарий
    await message.answer(text="⚙️ Админ-панель магазина:",
                         reply_markup=kb.inline_admin_panel)


@admin.callback_query(F.data == "add_product")
async def add_product(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.edit_text(text="➕ Что нужно добавить?", 
                                  reply_markup=kb.panel_add)


@admin.callback_query(F.data == "add_category")
async def add_category_name(callbback: CallbackQuery, state: FSMContext):
    await callbback.answer("")
    await callbback.message.answer("✏️ Введите название категории:")
    await state.set_state(kb.AddCategory.waiting_for_title)


@admin.message(kb.AddCategory.waiting_for_title, F.text)
async def add_category_base(message: Message, state: FSMContext):
    title = clean_text(message.text, CATEGORY_NAME_MAX_LENGTH)
    try:
        if not title:
            await message.answer(f"❌ Название должно быть от 1 до {CATEGORY_NAME_MAX_LENGTH} символов. Введите снова:")
            return 
        await state.update_data(title=title)
        await rq.add_category_database(title)
        await message.answer(f"✅ Категория '{title}' успешно добавлена!")
        await state.clear() 
        
    except IntegrityError:
        await message.answer(f"❌ Категория '{title}' уже существует! Введите другое название:")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")
        await state.clear()


@admin.callback_query(F.data == "add_card")
async def add_card_category(callback: CallbackQuery, state: FSMContext):
    await callback.answer("")
    await callback.message.answer("📁 Выберите категорию товара:", 
                                  reply_markup= await kb.categories_admin())
    await state.set_state(kb.AddCard.category)


@admin.callback_query(F.data.startswith("categoryes_"))
async def add_card_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer("")
    category_id = int(callback.data.split("_")[1])
    await state.update_data(category_id=category_id)
    await callback.message.answer("✏️ Введите название товара:")
    await state.set_state(kb.AddCard.name)


@admin.message(kb.AddCard.name, F.text)
async def add_card_price(message: Message, state: FSMContext):
    name = clean_text(message.text, CARD_NAME_MAX_LENGTH)
    if not name:
        await message.answer(f"❌ Название должно быть от 1 до {CARD_NAME_MAX_LENGTH} символов. Введите снова:")
        return
    await state.update_data(name=name)
    await message.answer("💰 Введите цену товара (целым числом):")
    await state.set_state(kb.AddCard.price)


@admin.message(kb.AddCard.price, F.text)
async def add_card_description(message: Message, state: FSMContext):
    price = parse_price(message.text)
    if price is None:
        await message.answer(f"❌ Цена должна быть целым числом от 1 до {MAX_PRICE}. Введите снова:")
        return
    await state.update_data(price=price)
    await message.answer("📝 Напишите описание товара:")
    await state.set_state(kb.AddCard.description)


@admin.message(kb.AddCard.description, F.text)
async def add_card_photo(message: Message, state: FSMContext):
    description = clean_text(message.text, CARD_DESCRIPTION_MAX_LENGTH)
    if not description:
        await message.answer(
            f"❌ Описание должно быть от 1 до {CARD_DESCRIPTION_MAX_LENGTH} символов. Введите снова:"
        )
        return
    await state.update_data(description=description, photos=[])
    await message.answer(PHOTOS_PROMPT)
    await state.set_state(kb.AddCard.photo)


PHOTOS_PROMPT = (
    f"🖼 Отправьте фото товара: по одному или альбомом, до {MAX_CARD_PHOTOS} шт.\n"
    "Первое фото станет обложкой. Когда закончите, нажмите «✅ Готово»."
)


@admin.message(StateFilter(kb.AddCard.photo, kb.EditCard.photos), F.photo)
async def collect_card_photo(message: Message, state: FSMContext):
    """Копит фото в FSM. Сообщения альбома приходят по одному, но обрабатываются строго
    по очереди благодаря SimpleEventIsolation в run.py, поэтому фото не теряются"""
    data = await state.get_data()
    photos = data.get("photos", [])
    album_id = message.media_group_id
    is_same_album = album_id is not None and album_id == data.get("last_album_id")

    if len(photos) >= MAX_CARD_PHOTOS:
        if not is_same_album:
            await message.answer(f"⚠️ Максимум {MAX_CARD_PHOTOS} фото, лишние не добавлены.",
                                 reply_markup=kb.photos_done)
        await state.update_data(last_album_id=album_id)
        return

    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos, last_album_id=album_id)
    if is_same_album:
        return  # на альбом отвечаем один раз, а не на каждое фото
    if album_id:
        await message.answer("📸 Альбом принят. Отправьте ещё фото или нажмите «✅ Готово».",
                             reply_markup=kb.photos_done)
    else:
        await message.answer(f"📸 Фото {len(photos)}/{MAX_CARD_PHOTOS} добавлено. "
                             "Отправьте ещё или нажмите «✅ Готово».",
                             reply_markup=kb.photos_done)


@admin.callback_query(F.data == "photos_done", StateFilter(kb.AddCard.photo, kb.EditCard.photos))
async def photos_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await callback.answer("Сначала отправьте хотя бы одно фото", show_alert=True)
        return
    await callback.answer()

    if await state.get_state() == kb.AddCard.photo.state:
        is_saved = await rq.add_card_database(
            data["category_id"], data["name"], data["price"], data["description"], photos
        )
        success_text = f"✅ Карточка создана, фото: {len(photos)}."
        error_text = "❌ Не удалось создать карточку, подробности в логах."
    else:
        is_saved = await rq.replace_card_photos(data["card_id"], photos)
        success_text = f"✅ Фото товара обновлены, теперь их {len(photos)}."
        error_text = "❌ Товар не найден: возможно, его уже удалили."

    await state.clear()
    await callback.message.answer(success_text if is_saved else error_text)
    if is_saved and "card_id" in data:
        await show_card_edit_menu(callback.message, data["card_id"])


@admin.callback_query(F.data == "photos_done")  # кнопка из старого сообщения
async def photos_done_outdated(callback: CallbackQuery):
    await callback.answer("Этот шаг уже завершён", show_alert=True)


@admin.message(StateFilter(kb.AddCard.photo, kb.EditCard.photos))
async def add_card_photo_invalid(message: Message):
    await message.answer("❌ Нужна именно фотография. Отправьте фото или нажмите «✅ Готово».",
                         reply_markup=kb.photos_done)


def parse_category_page(callback_data: str) -> tuple[int, int]:
    """prefix_{category_id} или prefix_{category_id}_{page} -> (category_id, page)"""
    parts = callback_data.split("_")
    return int(parts[1]), int(parts[2]) if len(parts) > 2 else 0


async def show_or_edit(callback: CallbackQuery, text: str, keyboard):
    """Листание и «Назад» редактируют сообщение со списком, первый показ — новым сообщением"""
    if len(callback.data.split("_")) > 2:
        with suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=keyboard)
    else:
        await callback.message.answer(text, reply_markup=keyboard)


@admin.callback_query(F.data == "remove_product")
async def delete_product(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.edit_text("🗑 Что нужно удалить?", reply_markup=kb.panel_del)


@admin.callback_query(F.data == "del_card")
async def delete_card(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.answer("📁 Выберите категорию, в которой карточка:",
                                  reply_markup=await kb.categories_admin_del())


@admin.callback_query(F.data.startswith("cat_"))  # cat_{id} или cat_{id}_{страница}
async def get_category_name(callback: CallbackQuery):
    await callback.answer("")
    category_id, page = parse_category_page(callback.data)
    await show_or_edit(callback, "🗑 Выберите карточку для удаления:",
                       await kb.cards_admin(category_id, page))


@admin.callback_query(F.data.startswith("carda_"))
async def get_card_name(callback: CallbackQuery):
    await callback.answer("")
    card_id = int(callback.data.split("_")[1])
    try:
        await rq.del_card_database(card_id)
        await callback.message.answer("✅ Успешно удалено!")
    except Exception as e:
        await callback.message.answer(f"❌ Произошла ошибка '{e}'.")


@admin.callback_query(F.data == "del_category")
async def del_category_name(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.answer(
        "⚠️ Выберите категорию для удаления (карточки этой категории тоже удалятся!):",
                                  reply_markup=await kb.categories_admin_2del()
    )


@admin.callback_query(F.data.startswith("cate_"))
async def del_category(callback: CallbackQuery):
    await callback.answer("")
    category_id = int(callback.data.split("_")[1])
    try:
        await rq.delete_category_database(category_id)
        await callback.message.answer("✅ Успешно удалено!")
    except Exception as e:
        await callback.message.answer(f"❌ Не удалось удалить, ошибка: '{e}'")

@admin.callback_query(F.data == "edit_card")
async def edit_card_choose_category(callback: CallbackQuery, state: FSMContext):
    await callback.answer("")
    await state.clear()
    await callback.message.answer("📁 Выберите категорию товара:",
                                  reply_markup=await kb.categories_admin_edit())


@admin.callback_query(F.data.startswith("ecat_"))  # ecat_{id} или ecat_{id}_{страница}
async def edit_card_choose_card(callback: CallbackQuery, state: FSMContext):
    await callback.answer("")
    await state.clear()
    category_id, page = parse_category_page(callback.data)
    await show_or_edit(callback, "✏️ Выберите товар для редактирования:",
                       await kb.cards_admin_edit(category_id, page))


async def show_card_edit_menu(message: Message, card_id: int):
    card = await get_card(card_id)
    if not card:
        await message.answer("❌ Товар не найден: возможно, его уже удалили.")
        return
    photos_count = len(await get_card_photos(card_id))
    await message.answer(
        f"✏️ Редактирование товара\n\n"
        f"📦 {card.name}\n"
        f"💰 {card.price} ₽\n"
        f"📝 {card.description}\n"
        f"🖼 Фото: {photos_count}\n\n"
        f"Что изменить?",
        reply_markup=kb.card_edit_menu(card.id, card.category_id),
    )


@admin.callback_query(F.data.startswith("ecard_"))  # ecard_{id}_{страница}
async def edit_card_menu(callback: CallbackQuery):
    await callback.answer("")
    await show_card_edit_menu(callback.message, int(callback.data.split("_")[1]))


EDIT_FIELD_PROMPTS = {
    "name": f"✏️ Введите новое название (до {CARD_NAME_MAX_LENGTH} символов):",
    "price": f"💰 Введите новую цену (целое число от 1 до {MAX_PRICE}):",
    "description": f"📝 Введите новое описание (до {CARD_DESCRIPTION_MAX_LENGTH} символов):",
}


@admin.callback_query(F.data.startswith("efield_"))  # efield_{поле}_{card_id}
async def edit_card_field_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer("")
    _, field, card_id = callback.data.split("_")
    await state.update_data(card_id=int(card_id), field=field, photos=[])
    if field == "photos":
        await callback.message.answer("Текущие фото будут заменены.\n\n" + PHOTOS_PROMPT)
        await state.set_state(kb.EditCard.photos)
    else:
        await callback.message.answer(EDIT_FIELD_PROMPTS[field])
        await state.set_state(kb.EditCard.value)


def parse_card_field(field: str, text: str) -> str | int | None:
    if field == "name":
        return clean_text(text, CARD_NAME_MAX_LENGTH)
    if field == "price":
        return parse_price(text)
    return clean_text(text, CARD_DESCRIPTION_MAX_LENGTH)


@admin.message(kb.EditCard.value, F.text)
async def edit_card_field_save(message: Message, state: FSMContext):
    data = await state.get_data()
    value = parse_card_field(data["field"], message.text)
    if value is None:
        await message.answer("❌ Некорректное значение. " + EDIT_FIELD_PROMPTS[data["field"]])
        return
    is_updated = await rq.update_card_field(data["card_id"], data["field"], value)
    await state.clear()
    if not is_updated:
        await message.answer("❌ Товар не найден: возможно, его уже удалили.")
        return
    await message.answer("✅ Сохранено!")
    await show_card_edit_menu(message, data["card_id"])


MAX_SETTING_TEXT_LENGTH = 1000


async def ask_new_setting_text(callback: CallbackQuery, state: FSMContext, new_state, title: str, current_text: str):
    await callback.answer("")
    await callback.message.answer(
        f"{title}\n\n{current_text}\n\n"
        f"✏️ Отправьте новый текст (до {MAX_SETTING_TEXT_LENGTH} символов):"
    )
    await state.set_state(new_state)


def is_valid_setting_text(text: str) -> bool:
    return 0 < len(text) <= MAX_SETTING_TEXT_LENGTH


@admin.callback_query(F.data == "edit_shop_description")
async def edit_shop_description_start(callback: CallbackQuery, state: FSMContext):
    await ask_new_setting_text(
        callback, state, kb.EditShopDescription.waiting_for_text,
        "📝 Текущее описание:", await get_shop_description()
    )


@admin.message(kb.EditShopDescription.waiting_for_text, F.text)
async def edit_shop_description_save(message: Message, state: FSMContext):
    new_description = message.text.strip()
    if not is_valid_setting_text(new_description):
        await message.answer(
            f"❌ Описание должно быть от 1 до {MAX_SETTING_TEXT_LENGTH} символов. Введите снова:"
        )
        return
    await rq.set_shop_description(new_description)
    await message.answer("✅ Описание магазина обновлено!")
    await state.clear()


@admin.callback_query(F.data == "edit_shop_contacts")
async def edit_shop_contacts_start(callback: CallbackQuery, state: FSMContext):
    await ask_new_setting_text(
        callback, state, kb.EditShopContacts.waiting_for_text,
        "📞 Текущие контакты:", await get_shop_contacts()
    )


@admin.message(kb.EditShopContacts.waiting_for_text, F.text)
async def edit_shop_contacts_save(message: Message, state: FSMContext):
    new_contacts = message.text.strip()
    if not is_valid_setting_text(new_contacts):
        await message.answer(
            f"❌ Текст контактов должен быть от 1 до {MAX_SETTING_TEXT_LENGTH} символов. Введите снова:"
        )
        return
    await rq.set_shop_contacts(new_contacts)
    await message.answer("✅ Контакты обновлены!")
    await state.clear()


# Регистрируется последним: ловит стикеры, фото и т.п. там, где админка ждёт текст
@admin.message(StateFilter(
    kb.AddCategory.waiting_for_title,
    kb.AddCard.name,
    kb.AddCard.price,
    kb.AddCard.description,
    kb.EditCard.value,
    kb.EditShopDescription.waiting_for_text,
    kb.EditShopContacts.waiting_for_text,
))
async def text_expected(message: Message):
    await message.answer("❌ Здесь нужен текст. Отправьте его ещё раз:")
