from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext


from sqlalchemy.exc import IntegrityError, SQLAlchemyError


import app.keyboards as kb
from app.filters import IsAdmin
import app.database.requests_admin as rq
from app.database.requests import get_shop_description, get_shop_contacts
import logging


admin = Router()
admin.message.filter(IsAdmin())
admin.callback_query.filter(IsAdmin())


logger = logging.getLogger(__name__)


@admin.message(Command("admin"))
async def admin_panel(message: Message):
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


@admin.message(kb.AddCategory.waiting_for_title)  
async def add_category_base(message: Message, state: FSMContext):
    title = message.text.strip() 
    try:
        if not title:
            await message.answer("❌ Название не может быть пустым. Введите снова:")
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


@admin.message(kb.AddCard.name)
async def add_card_price(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("💰 Введите цену товара (целым числом):")
    await state.set_state(kb.AddCard.price)


@admin.message(kb.AddCard.price)
async def add_card_description(message: Message, state: FSMContext):
    price = (message.text or "").strip()
    if not price.isdigit():
        await message.answer("❌ Цена должна быть целым числом. Введите снова:")
        return
    await state.update_data(price=int(price))
    await message.answer("📝 Напишите описание товара:")
    await state.set_state(kb.AddCard.description)


@admin.message(kb.AddCard.description)
async def add_card_photo(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer("🖼 Отправьте фото товара:")
    await state.set_state(kb.AddCard.photo)


@admin.message(kb.AddCard.photo, F.photo)
async def add_card_(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    data = await state.get_data()
    is_added = await rq.add_card_database(
        data["category_id"], data["name"], data["price"], data["description"], data["photo"]
    )
    if is_added:
        await message.answer("✅ Карточка успешно создана!")
    else:
        await message.answer("❌ Не удалось создать карточку, подробности в логах.")
    await state.clear()


@admin.message(kb.AddCard.photo)
async def add_card_photo_invalid(message: Message):
    await message.answer("❌ Нужна именно фотография. Отправьте фото товара:")


@admin.callback_query(F.data == "remove_product")
async def delete_product(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.edit_text("🗑 Что нужно удалить?", reply_markup=kb.panel_del)


@admin.callback_query(F.data == "del_card")
async def delete_card(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.answer("📁 Выберите категорию, в которой карточка:",
                                  reply_markup=await kb.categories_admin_del())


@admin.callback_query(F.data.startswith("cat_"))
async def get_category_name(callback: CallbackQuery):
    await callback.answer("")
    category_id = int(callback.data.split("_")[1])
    await callback.message.answer("🗑 Выберите карточку для удаления:",
                                  reply_markup=await kb.cards_admin(category_id))


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
