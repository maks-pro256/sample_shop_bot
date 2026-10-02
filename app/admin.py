from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext


from sqlalchemy.exc import IntegrityError, SQLAlchemyError


import app.keyboards as kb
import app.database.requests_admin as rq
import logging


admin = Router()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@admin.message(Command("admin"))
async def admin_panel(message: Message):
    await message.answer(text="Приветсвую, будущий админ!", 
                         reply_markup=kb.inline_admin_panel)


@admin.callback_query(F.data == "add_product")
async def add_product(callback: CallbackQuery):
    await callback.answer("добавить")
    await callback.message.edit_text(text="Что нужно добавить?", 
                                  reply_markup=kb.panel_add)


@admin.callback_query(F.data == "add_category")
async def add_category_name(callbback: CallbackQuery, state: FSMContext):
    await callbback.answer("категории")
    await callbback.message.answer("Введите название категории:")
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
    await callback.message.answer("Выберите категорию товара:", 
                                  reply_markup= await kb.categories_admin())
    await state.set_state(kb.AddCard.category)


@admin.callback_query(F.data.startswith("categoryes_"))
async def add_card_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer("")
    category = callback.data.split("_")[1]
    await state.update_data(category=category)
    await callback.message.answer("Введите название товара:")
    await state.set_state(kb.AddCard.name)


@admin.message(kb.AddCard.name)
async def add_card_price(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Введите цену товара:")
    await state.set_state(kb.AddCard.price)


@admin.message(kb.AddCard.price)
async def add_card_description(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await message.answer("Напишите описание товара:")
    await state.set_state(kb.AddCard.description)


@admin.message(kb.AddCard.description)
async def add_card_photo(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer("Отправьте фотку товара:")
    await state.set_state(kb.AddCard.photo)


@admin.message(kb.AddCard.photo)
async def add_card_(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    data = await state.get_data()
    try:
        await rq.add_card_database(
            data["category"], data["name"], data["price"], data["description"], data["photo"]
        )
        await message.answer("Карточка успешно создана!")
        await state.clear()
    except Exception as e:
        await message.answer(f"Произошла ошибка '{e}'.")
        await state.clear()


@admin.callback_query(F.data == "remove_product")
async def delete_product(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.edit_text("Выберите:", reply_markup=kb.panel_del)


@admin.callback_query(F.data == "del_card")
async def delete_card(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.answer("Выберите категорию, в которой карточка:",
                                  reply_markup=await kb.categories_admin_del())


@admin.callback_query(F.data.startswith("cat_"))
async def get_category_name(callback: CallbackQuery):
    await callback.answer("")
    category = callback.data.split("_")[1]
    await callback.message.answer("Выберите карточку для удаления:",
                                  reply_markup=await kb.cards_admin(category))


@admin.callback_query(F.data.startswith("carda_"))
async def get_card_name(callback: CallbackQuery):
    await callback.answer("")
    card = callback.data.split("_")[1]
    try:
        await rq.del_card_database(card)
        await callback.message.answer("Успешно удалено!")
    except Exception as e:
        await callback.message.answer(f"Произошла ошибка '{e}'.")


@admin.callback_query(F.data == "del_category")
async def del_category_name(callback: CallbackQuery):
    await callback.answer("")
    await callback.message.answer(
        "Выберите категорию для удаления (при удалении категории и все карточки этой категории тоже удаляются!):",
                                  reply_markup=await kb.categories_admin_2del()
    )


@admin.callback_query(F.data.startswith("cate_"))
async def del_category(callback: CallbackQuery):
    await callback.answer("")
    name = callback.data.split("_")[1]
    await rq.delete_category_database(name)
    try:
        await callback.message.answer("Успешно удалено!")
    except Exception as e:
        await callback.message.answer("Не удалось удалить, ошибка: '{e}'")