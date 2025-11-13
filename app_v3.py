import asyncio
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from functools import wraps

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

# Попытка загрузить python-dotenv (опционально)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------- CONFIG ----------------

@dataclass
class Settings:
    bot_token: str
    superadmins: List[int]
    db_path: str = "salary_bot.db"


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

    superadmins_raw = os.getenv("SUPERADMIN_IDS", "").strip()
    if not superadmins_raw:
        raise RuntimeError("Не задан SUPERADMIN_IDS (через запятую).")

    superadmins = [int(x) for x in superadmins_raw.split(",") if x.strip()]
    db_path = os.getenv("DB_PATH", "salary_bot.db")

    return Settings(bot_token=token, superadmins=superadmins, db_path=db_path)


settings = load_settings()


# ---------------- БАЗА ДАННЫХ ----------------

def get_db():
    """Создаёт подключение к БД с поддержкой Row."""
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализирует базу данных с таблицами и индексами."""
    with get_db() as conn:
        cur = conn.cursor()

        # Таблица отделов
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                emoji TEXT
            );
            """
        )

        # Таблица сотрудников
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                telegram_user_id INTEGER UNIQUE,
                department_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('employee', 'manager')),
                position TEXT,
                salary REAL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (department_id) REFERENCES departments(id)
            );
            """
        )

        # Таблица начислений
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accruals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('salary', 'bonus', 'deduction', 'advance', 'payout')),
                comment TEXT,
                period TEXT,
                created_at TEXT NOT NULL,
                created_by INTEGER,
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            );
            """
        )

        # Создаём индексы для производительности
        cur.execute("CREATE INDEX IF NOT EXISTS idx_employees_telegram_user_id ON employees(telegram_user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_employees_department_id ON employees(department_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_accruals_employee_id ON accruals(employee_id)")

        conn.commit()


def import_company_structure():
    """Импортирует структуру компании 'Автозапчасть' в базу данных."""
    with get_db() as conn:
        cur = conn.cursor()
        
        # Проверяем, есть ли уже данные
        cur.execute("SELECT COUNT(*) as cnt FROM departments")
        if cur.fetchone()["cnt"] > 0:
            logging.info("База данных уже содержит данные, импорт пропущен")
            return
        
        logging.info("Импорт структуры компании...")
        
        # 1. Создаём отделы
        departments = {
            "Отдел выкупа": "💸",
            "Отдел продаж": "🧾",
            "Склад (производство)": "📦",
            "PR-отдел": "📣",
            "Отдел разбора": "🧰",
            "Бухгалтерия": "🧮"
        }
        
        dept_ids = {}
        for dept_name, emoji in departments.items():
            cur.execute(
                "INSERT INTO departments (name, emoji) VALUES (?, ?)",
                (dept_name, emoji)
            )
            dept_ids[dept_name] = cur.lastrowid
        
        # 2. Добавляем сотрудников
        
        # Отдел выкупа
        employees_vykup = [
            ("Захаркин Андрей Андреевич", "менеджер по выкупу"),
            ("Макарова Лилия Сергеевна", "оператор колл-центра"),
            ("Михайленков Алексей Викторович", "менеджер по выкупу"),
            ("Пославская Юлия Ивановна", "оператор колл-центра"),
            ("Широ Татьяна Ивановна", "руководитель колл-центра"),
        ]
        
        for name, position in employees_vykup:
            cur.execute(
                "INSERT INTO employees (full_name, department_id, role, position, is_active) VALUES (?, ?, 'employee', ?, 1)",
                (name, dept_ids["Отдел выкупа"], position)
            )
        
        # Отдел продаж
        cur.execute(
            "INSERT INTO employees (full_name, department_id, role, position, is_active) VALUES (?, ?, 'manager', ?, 1)",
            ("Артамонов Дмитрий Сергеевич", dept_ids["Отдел продаж"], "руководитель отдела продаж")
        )
        
        employees_sales = [
            ("Филимонов Игорь Павлович", "менеджер по продажам"),
            ("Дериглазов Виктор Васильевич", "менеджер по продажам"),
            ("Серков Виталий Андреевич", "менеджер по продажам"),
            ("Джумакашева Марина Васильевна", "кассир"),
            ("Ефремова Ангелина Ивановна", "кассир"),
            ("Клюкин Владимир Олегович", "менеджер по продажам"),
            ("Ломас Кирилл Алексеевич", "менеджер по продажам"),
            ("Овчинников Данил Витальевич", "менеджер по продажам"),
            ("Темерке Дмитрий Николаевич", "менеджер по продажам"),
            ("Сергеева Лариса Анатольевна", "кассир"),
            ("Куриленко Ксения Сергеевна", "менеджер по продажам"),
            ("Шабуров Артём Владимирович", "менеджер по продажам"),
        ]
        
        for name, position in employees_sales:
            cur.execute(
                "INSERT INTO employees (full_name, department_id, role, position, is_active) VALUES (?, ?, 'employee', ?, 1)",
                (name, dept_ids["Отдел продаж"], position)
            )
        
        # Склад (производство) - руководитель Черезов Леонид
        employees_warehouse = [
            ("Агафонов Виталий", "кладовщик"),
            ("Бурматов Дмитрий", "кладовщик"),
            ("Быковский Максим", "кладовщик"),
            ("Выбрик Александр Валерьевич", "кладовщик"),
            ("Гарус Игорь", "кладовщик"),
            ("Горбунов Александр", "кладовщик"),
            ("Гречихин Владимир Анатольевич", "кладовщик"),
            ("Макаров Алексей", "кладовщик"),
            ("Новосёлов Александр Сергеевич", "сварщик"),
            ("Шадрин Евгений", "кладовщик"),
            ("Подберёзный Игорь Романович", "кладовщик"),
            ("Попов Максим Андреевич", "кладовщик"),
            ("Привалов Владимир Геннадьевич", "старший кладовщик"),
            ("Романов Александр Викторович", "кладовщик"),
            ("Сероштан Владимир Фёдорович", "разнорабочий"),
            ("Соколов Дмитрий Николаевич", "кладовщик"),
            ("Сулейманов Ринат Тимершатович", "кладовщик"),
            ("Цветков Николай", "кладовщик"),
            ("Шулепова Ульяна Алексеевна", "уборщица"),
            ("Валерий Ловягин", "разнорабочий"),
            ("Сиваченко Юрий", "кладовщик"),
            ("Хисматуллин Артур Рафикович", "кладовщик"),
            ("Мухутдинов Эдуард", "кладовщик"),
            ("Валько Владислав", "кладовщик"),
        ]
        
        for name, position in employees_warehouse:
            cur.execute(
                "INSERT INTO employees (full_name, department_id, role, position, is_active) VALUES (?, ?, 'employee', ?, 1)",
                (name, dept_ids["Склад (производство)"], position)
            )
        
        # PR-отдел - руководитель тоже Черезов Леонид
        employees_pr = [
            ("Солдатова Екатерина Валерьевна", "блогер"),
            ("Курсов Перун Андреевич (Данил)", "блогер"),
            ("Герасименко Андрей Иванович", "оператор-монтажёр"),
        ]
        
        for name, position in employees_pr:
            cur.execute(
                "INSERT INTO employees (full_name, department_id, role, position, is_active) VALUES (?, ?, 'employee', ?, 1)",
                (name, dept_ids["PR-отдел"], position)
            )
        
        # Отдел разбора
        cur.execute(
            "INSERT INTO employees (full_name, department_id, role, position, is_active) VALUES (?, ?, 'manager', ?, 1)",
            ("Первухин Алексей", dept_ids["Отдел разбора"], "руководитель отдела разбора")
        )
        
        employees_razbor = [
            ("Калугин Максим", "проценщик"),
            ("Попов Максим", "проценщик"),
            ("Кокшаров Виталий", "разборщик"),
            ("Кудрявцев Сергей", "разборщик"),
            ("Клюкин Денис", "проценщик"),
            ("Матюшенко Александр", "проценщик"),
            ("Шульц Максим", "подготовщик"),
        ]
        
        for name, position in employees_razbor:
            cur.execute(
                "INSERT INTO employees (full_name, department_id, role, position, is_active) VALUES (?, ?, 'employee', ?, 1)",
                (name, dept_ids["Отдел разбора"], position)
            )
        
        # Бухгалтерия
        employees_buh = [
            ("Назырова Анна", "бухгалтер"),
            ("Виктория (фамилия уточняется)", "бухгалтер"),
        ]
        
        for name, position in employees_buh:
            cur.execute(
                "INSERT INTO employees (full_name, department_id, role, position, is_active) VALUES (?, ?, 'employee', ?, 1)",
                (name, dept_ids["Бухгалтерия"], position)
            )
        
        conn.commit()
        logging.info(f"✅ Импортировано {len(dept_ids)} отделов и все сотрудники")


# ---------------- УТИЛИТЫ ПО РОЛЯМ ----------------

ROLE_SUPERADMIN = "superadmin"
ROLE_MANAGER = "manager"
ROLE_EMPLOYEE = "employee"
ROLE_UNKNOWN = "unknown"


def get_user_role(user_id: int) -> str:
    """Определяет роль пользователя по его Telegram ID."""
    if user_id in settings.superadmins:
        return ROLE_SUPERADMIN

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT role FROM employees WHERE telegram_user_id = ? AND is_active = 1",
                (user_id,),
            )
            row = cur.fetchone()

            if row:
                return ROLE_MANAGER if row["role"] == "manager" else ROLE_EMPLOYEE
    except Exception as e:
        logging.error(f"Ошибка при получении роли пользователя {user_id}: {e}")

    return ROLE_UNKNOWN


def require_role(*allowed_roles):
    """Декоратор для проверки роли пользователя."""
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            role = get_user_role(message.from_user.id)
            if role not in allowed_roles:
                await message.answer("❌ У вас нет доступа к этой функции.")
                return
            return await handler(message, *args, **kwargs)
        return wrapper
    return decorator


def get_manager_departments(user_id: int) -> List[int]:
    """Получает список ID отделов, которыми управляет менеджер."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT department_id FROM employees WHERE telegram_user_id = ? AND role = 'manager' AND is_active = 1",
                (user_id,),
            )
            return [row["department_id"] for row in cur.fetchall()]
    except Exception as e:
        logging.error(f"Ошибка при получении отделов менеджера {user_id}: {e}")
        return []


def get_department_employees(department_id: int) -> List[sqlite3.Row]:
    """Получает список сотрудников отдела."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, full_name, position, role FROM employees WHERE department_id = ? AND is_active = 1 ORDER BY full_name",
                (department_id,),
            )
            return cur.fetchall()
    except Exception as e:
        logging.error(f"Ошибка при получении сотрудников отдела {department_id}: {e}")
        return []


def add_employee(full_name: str, department_id: int, role: str, position: str = "", telegram_user_id: Optional[int] = None):
    """Добавляет нового сотрудника в базу."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO employees (full_name, telegram_user_id, department_id, role, position, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (full_name, telegram_user_id, department_id, role, position),
            )
            conn.commit()
            logging.info(f"Добавлен сотрудник: {full_name} в отдел {department_id}")
    except Exception as e:
        logging.error(f"Ошибка при добавлении сотрудника {full_name}: {e}")
        raise


def add_department(name: str, emoji: str = "") -> int:
    """Добавляет новый отдел."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO departments (name, emoji) VALUES (?, ?)",
                (name, emoji),
            )
            dept_id = cur.lastrowid
            conn.commit()
            logging.info(f"Добавлен отдел: {name} (ID: {dept_id})")
            return dept_id
    except Exception as e:
        logging.error(f"Ошибка при добавлении отдела {name}: {e}")
        raise


def get_departments() -> List[sqlite3.Row]:
    """Получает список всех отделов."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, emoji FROM departments ORDER BY id")
            return cur.fetchall()
    except Exception as e:
        logging.error(f"Ошибка при получении списка отделов: {e}")
        return []


def add_accrual(employee_id: int, amount: float, kind: str, comment: str, created_by: int):
    """Добавляет начисление/выплату."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO accruals (employee_id, amount, kind, comment, created_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (employee_id, amount, kind, comment, datetime.now(timezone.utc).isoformat(), created_by),
            )
            conn.commit()
            logging.info(f"Начисление {kind}: {amount} руб. для сотрудника {employee_id}")
    except Exception as e:
        logging.error(f"Ошибка при добавлении начисления: {e}")
        raise


def get_employee_balance(employee_id: int) -> float:
    """Вычисляет баланс сотрудника."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN kind IN ('salary', 'bonus') THEN amount ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN kind IN ('payout', 'advance', 'deduction') THEN amount ELSE 0 END), 0)
                AS balance
                FROM accruals
                WHERE employee_id = ?
                """,
                (employee_id,),
            )
            row = cur.fetchone()
            return row["balance"] if row and row["balance"] is not None else 0.0
    except Exception as e:
        logging.error(f"Ошибка при вычислении баланса сотрудника {employee_id}: {e}")
        return 0.0


def get_employee_by_name(full_name: str, department_id: Optional[int] = None):
    """Получает сотрудника по имени."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            # Убираем эмодзи из имени
            clean_name = full_name.replace("👤", "").replace("👔", "").strip()
            
            if department_id:
                cur.execute(
                    "SELECT * FROM employees WHERE full_name = ? AND department_id = ? AND is_active = 1",
                    (clean_name, department_id)
                )
            else:
                cur.execute(
                    "SELECT * FROM employees WHERE full_name = ? AND is_active = 1",
                    (clean_name,)
                )
            return cur.fetchone()
    except Exception as e:
        logging.error(f"Ошибка при поиске сотрудника {full_name}: {e}")
        return None


def get_employee_accruals(employee_id: int, period: Optional[str] = None):
    """Получает список начислений сотрудника."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            if period:
                cur.execute(
                    """
                    SELECT * FROM accruals 
                    WHERE employee_id = ? AND period = ?
                    ORDER BY created_at DESC
                    """,
                    (employee_id, period)
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM accruals 
                    WHERE employee_id = ?
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    (employee_id,)
                )
            return cur.fetchall()
    except Exception as e:
        logging.error(f"Ошибка при получении начислений сотрудника {employee_id}: {e}")
        return []


def get_employee_salary(employee_id: int) -> float:
    """Получает оклад сотрудника."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT salary FROM employees WHERE id = ?", (employee_id,))
            row = cur.fetchone()
            return row["salary"] if row and row["salary"] else 0.0
    except Exception as e:
        logging.error(f"Ошибка при получении оклада сотрудника {employee_id}: {e}")
        return 0.0


def set_employee_salary(employee_id: int, salary: float):
    """Устанавливает оклад сотрудника."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE employees SET salary = ? WHERE id = ?",
                (salary, employee_id)
            )
            conn.commit()
            logging.info(f"Установлен оклад {salary} для сотрудника {employee_id}")
    except Exception as e:
        logging.error(f"Ошибка при установке оклада: {e}")
        raise


def validate_amount(amount_str: str) -> Optional[float]:
    """Валидирует и парсит денежную сумму."""
    try:
        amount = float(amount_str.replace(",", ".").strip())
        return amount if amount > 0 else None
    except ValueError:
        return None


# ---------------- КЛАВИАТУРЫ ----------------

def superadmin_main_kb() -> ReplyKeyboardMarkup:
    """Главная клавиатура суперадмина."""
    departments = get_departments()
    buttons = []
    
    for dept in departments:
        emoji = dept['emoji'] or '🏢'
        buttons.append([KeyboardButton(text=f"{emoji} {dept['name']}")])

    buttons.append([KeyboardButton(text="📊 Все сотрудники")])
    buttons.append([KeyboardButton(text="➕ Добавить сотрудника")])
    buttons.append([KeyboardButton(text="➕ Добавить отдел")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def manager_main_kb() -> ReplyKeyboardMarkup:
    """Главная клавиатура менеджера."""
    kb = [
        [KeyboardButton(text="👥 Мои сотрудники")],
        [KeyboardButton(text="💵 Начислить зарплату")],
        [KeyboardButton(text="➕ Добавить сотрудника")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def employee_main_kb() -> ReplyKeyboardMarkup:
    """Главная клавиатура сотрудника."""
    kb = [
        [KeyboardButton(text="📊 Моя зарплата")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# ---------------- FSM СОСТОЯНИЯ ----------------

class AddEmployeeStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_position = State()
    waiting_for_department = State()


class AccrualStates(StatesGroup):
    waiting_for_employee = State()
    waiting_for_amount = State()
    waiting_for_comment = State()


class AddDepartmentStates(StatesGroup):
    waiting_for_name = State()


class SetSalaryStates(StatesGroup):
    waiting_for_employee_id = State()
    waiting_for_amount = State()


class AddBonusStates(StatesGroup):
    waiting_for_employee_id = State()
    waiting_for_amount = State()
    waiting_for_comment = State()


class AddDeductionStates(StatesGroup):
    waiting_for_employee_id = State()
    waiting_for_amount = State()
    waiting_for_comment = State()


# ---------------- РОУТЕР ----------------

router = Router()


# ----------- КОМАНДЫ -----------

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    role = get_user_role(message.from_user.id)

    if role == ROLE_SUPERADMIN:
        text = (
            f"👋 Здравствуйте, <b>Директор</b>!\n\n"
            f"Вы вошли как <b>SuperAdmin</b> компании «Автозапчасть».\n\n"
            f"Доступные функции:\n"
            f"• Просмотр всех отделов и сотрудников\n"
            f"• Добавление отделов и сотрудников\n"
            f"• Управление начислениями\n\n"
            f"Выберите действие на клавиатуре ниже:"
        )
        await message.answer(text, reply_markup=superadmin_main_kb(), parse_mode="HTML")
    elif role == ROLE_MANAGER:
        text = (
            f"👋 Здравствуйте, <b>Руководитель</b>!\n\n"
            f"Вы можете:\n"
            f"• Просматривать своих сотрудников\n"
            f"• Начислять зарплату\n"
            f"• Добавлять новых сотрудников\n\n"
            f"Выберите действие на клавиатуре:"
        )
        await message.answer(text, reply_markup=manager_main_kb(), parse_mode="HTML")
    elif role == ROLE_EMPLOYEE:
        text = (
            f"👋 Здравствуйте!\n\n"
            f"Вы можете просматривать информацию о своей зарплате.\n"
            f"Используйте кнопку ниже:"
        )
        await message.answer(text, reply_markup=employee_main_kb())
    else:
        text = (
            "👋 Здравствуйте!\n\n"
            "Вы пока не привязаны к системе зарплатного учёта.\n"
            "Обратитесь к руководителю отдела или директору для добавления в систему."
        )
        await message.answer(text, reply_markup=ReplyKeyboardRemove())


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка по командам."""
    role = get_user_role(message.from_user.id)
    
    if role == ROLE_SUPERADMIN:
        text = (
            "🔧 <b>Команды SuperAdmin:</b>\n\n"
            "• <b>[Отдел]</b> — просмотр сотрудников отдела\n"
            "• <b>📊 Все сотрудники</b> — полный список\n"
            "• <b>➕ Добавить сотрудника</b> — добавление в любой отдел\n"
            "• <b>➕ Добавить отдел</b> — создание нового отдела\n"
            "• <b>/start</b> — вернуться в главное меню\n"
        )
    elif role == ROLE_MANAGER:
        text = (
            "👔 <b>Команды руководителя:</b>\n\n"
            "• <b>👥 Мои сотрудники</b> — список вашего отдела\n"
            "• <b>💵 Начислить зарплату</b> — начисление сотруднику\n"
            "• <b>➕ Добавить сотрудника</b> — в ваш отдел\n"
            "• <b>/start</b> — вернуться в главное меню\n"
        )
    else:
        text = (
            "👤 <b>Доступные команды:</b>\n\n"
            "• <b>📊 Моя зарплата</b> — просмотр баланса начислений\n"
            "• <b>/start</b> — вернуться в главное меню\n"
        )
    
    await message.answer(text, parse_mode="HTML")


# ----------- СУПЕРАДМИН: ДОБАВИТЬ ОТДЕЛ -----------

@router.message(F.text == "➕ Добавить отдел")
@require_role(ROLE_SUPERADMIN)
async def superadmin_add_department_start(message: Message, state: FSMContext):
    """Начало добавления нового отдела."""
    await state.set_state(AddDepartmentStates.waiting_for_name)
    await message.answer(
        "Введите название нового отдела:\n\n"
        "Например: <i>Отдел маркетинга</i>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@router.message(AddDepartmentStates.waiting_for_name)
@require_role(ROLE_SUPERADMIN)
async def superadmin_add_department_finish(message: Message, state: FSMContext):
    """Завершение добавления отдела."""
    name = message.text.strip()
    if not name:
        await message.answer("❌ Пустое название. Введите название отдела:")
        return
    
    try:
        add_department(name)
        await state.clear()
        await message.answer(
            f"✅ Отдел «{name}» успешно добавлен!",
            reply_markup=superadmin_main_kb()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при добавлении отдела: {str(e)}",
            reply_markup=superadmin_main_kb()
        )
        await state.clear()


# ----------- ДОБАВИТЬ СОТРУДНИКА -----------

@router.message(F.text == "➕ Добавить сотрудника")
@require_role(ROLE_SUPERADMIN, ROLE_MANAGER)
async def add_employee_start(message: Message, state: FSMContext):
    """Начало добавления сотрудника."""
    await state.set_state(AddEmployeeStates.waiting_for_full_name)
    await message.answer(
        "Введите ФИО сотрудника:\n\n"
        "Например: <i>Иванов Иван Иванович</i>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@router.message(AddEmployeeStates.waiting_for_full_name)
@require_role(ROLE_SUPERADMIN, ROLE_MANAGER)
async def add_employee_enter_position(message: Message, state: FSMContext):
    """Ввод должности сотрудника."""
    full_name = message.text.strip()
    if not full_name:
        await message.answer("❌ Пустое имя. Введите ФИО сотрудника:")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(AddEmployeeStates.waiting_for_position)
    await message.answer(
        "Введите должность сотрудника:\n\n"
        "Например: <i>менеджер по продажам</i>",
        parse_mode="HTML"
    )


@router.message(AddEmployeeStates.waiting_for_position)
@require_role(ROLE_SUPERADMIN, ROLE_MANAGER)
async def add_employee_choose_department(message: Message, state: FSMContext):
    """Выбор отдела для сотрудника."""
    role = get_user_role(message.from_user.id)
    position = message.text.strip()
    
    if not position:
        await message.answer("❌ Пустая должность. Введите должность:")
        return
    
    await state.update_data(position=position)
    data = await state.get_data()
    full_name = data.get("full_name")

    # Менеджер добавляет только в свой отдел
    if role == ROLE_MANAGER:
        dept_ids = get_manager_departments(message.from_user.id)
        if not dept_ids:
            await message.answer(
                "❌ Не удалось определить ваш отдел. Обратитесь к директору.",
                reply_markup=manager_main_kb()
            )
            await state.clear()
            return
        
        try:
            add_employee(full_name=full_name, department_id=dept_ids[0], role="employee", position=position)
            await message.answer(
                f"✅ Сотрудник «{full_name}» ({position}) добавлен в ваш отдел!",
                reply_markup=manager_main_kb()
            )
        except Exception as e:
            await message.answer(
                f"❌ Ошибка при добавлении: {str(e)}",
                reply_markup=manager_main_kb()
            )
        await state.clear()
        return

    # Суперадмин выбирает отдел
    departments = get_departments()
    if not departments:
        await message.answer(
            "❌ Сначала создайте хотя бы один отдел через «➕ Добавить отдел».",
            reply_markup=superadmin_main_kb()
        )
        await state.clear()
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"{d['emoji'] or '🏢'} {d['name']}")] for d in departments],
        resize_keyboard=True,
    )
    await state.set_state(AddEmployeeStates.waiting_for_department)
    await message.answer("Выберите отдел для сотрудника:", reply_markup=kb)


@router.message(AddEmployeeStates.waiting_for_department)
@require_role(ROLE_SUPERADMIN)
async def add_employee_finish_superadmin(message: Message, state: FSMContext):
    """Завершение добавления сотрудника суперадмином."""
    data = await state.get_data()
    full_name = data.get("full_name")
    position = data.get("position")
    
    # Парсим название отдела (убираем эмодзи)
    dept_name_text = message.text
    for emoji in ["💸", "🧾", "📦", "📣", "🧰", "🧮", "🏢"]:
        dept_name_text = dept_name_text.replace(emoji, "").strip()

    departments = get_departments()
    dept_id = None
    for d in departments:
        if d["name"] == dept_name_text:
            dept_id = d["id"]
            break

    if not dept_id:
        await message.answer(
            "❌ Не удалось найти такой отдел. Выберите из списка на клавиатуре."
        )
        return

    try:
        add_employee(full_name=full_name, department_id=dept_id, role="employee", position=position)
        await state.clear()
        await message.answer(
            f"✅ Сотрудник «{full_name}» ({position}) добавлен в отдел «{dept_name_text}»!",
            reply_markup=superadmin_main_kb(),
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при добавлении: {str(e)}",
            reply_markup=superadmin_main_kb()
        )
        await state.clear()


# ----------- ПРОСМОТР СОТРУДНИКОВ -----------

@router.message(F.text == "📊 Все сотрудники")
@require_role(ROLE_SUPERADMIN)
async def superadmin_all_employees(message: Message):
    """Показывает всех сотрудников по отделам."""
    departments = get_departments()
    
    if not departments:
        await message.answer("В базе пока нет отделов.", reply_markup=superadmin_main_kb())
        return
    
    text = "📋 <b>Все сотрудники компании «Автозапчасть»</b>\n\n"
    
    for dept in departments:
        employees = get_department_employees(dept['id'])
        emoji = dept['emoji'] or '🏢'
        text += f"{emoji} <b>{dept['name']}</b>\n"
        
        if employees:
            for emp in employees:
                role_badge = "👔" if emp['role'] == 'manager' else "👤"
                position = f" ({emp['position']})" if emp['position'] else ""
                text += f"  {role_badge} {emp['full_name']}{position}\n"
        else:
            text += "  <i>Нет сотрудников</i>\n"
        
        text += "\n"
    
    await message.answer(text, parse_mode="HTML", reply_markup=superadmin_main_kb())


@router.message(F.text == "👥 Мои сотрудники")
@require_role(ROLE_MANAGER)
async def manager_my_employees(message: Message):
    """Показывает сотрудников менеджера."""
    dept_ids = get_manager_departments(message.from_user.id)
    
    if not dept_ids:
        await message.answer(
            "❌ Не найден ваш отдел. Обратитесь к директору.",
            reply_markup=manager_main_kb()
        )
        return
    
    text = "👥 <b>Мои сотрудники:</b>\n\n"
    
    for dept_id in dept_ids:
        employees = get_department_employees(dept_id)
        
        if employees:
            for emp in employees:
                position = f" ({emp['position']})" if emp['position'] else ""
                text += f"👤 {emp['full_name']}{position}\n"
        else:
            text += "<i>Нет сотрудников</i>\n"
    
    await message.answer(text, parse_mode="HTML", reply_markup=manager_main_kb())


# Обработка выбора отдела (для суперадмина)
@router.message(F.text.regexp(r"^[💸🧾📦📣🧰🧮🏢].+"))
@require_role(ROLE_SUPERADMIN)
async def superadmin_view_department(message: Message, state: FSMContext):
    """Просмотр сотрудников конкретного отдела."""
    dept_name = message.text
    for emoji in ["💸", "🧾", "📦", "📣", "🧰", "🧮", "🏢"]:
        dept_name = dept_name.replace(emoji, "").strip()
    
    departments = get_departments()
    dept_id = None
    for d in departments:
        if d["name"] == dept_name:
            dept_id = d["id"]
            break
    
    if not dept_id:
        await message.answer("❌ Отдел не найден", reply_markup=superadmin_main_kb())
        return
    
    employees = get_department_employees(dept_id)
    
    emoji = next((d['emoji'] for d in departments if d['id'] == dept_id), '🏢')
    
    if not employees:
        await message.answer(
            f"{emoji} <b>{dept_name}</b>\n\n<i>Нет сотрудников</i>",
            parse_mode="HTML",
            reply_markup=superadmin_main_kb()
        )
        return
    
    # Создаём кнопки для каждого сотрудника
    buttons = []
    for emp in employees:
        role_badge = "👔" if emp['role'] == 'manager' else "👤"
        buttons.append([KeyboardButton(text=f"{role_badge} {emp['full_name']}")])
    
    # Добавляем кнопку "Назад"
    buttons.append([KeyboardButton(text="⬅️ Назад в главное меню")])
    
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    
    # Сохраняем ID отдела в состоянии для обработки выбора сотрудника
    await state.update_data(current_department_id=dept_id, current_department_name=dept_name)
    
    await message.answer(
        f"{emoji} <b>{dept_name}</b>\n\nВыберите сотрудника:",
        parse_mode="HTML",
        reply_markup=kb
    )


# Кнопка "Назад в главное меню"
@router.message(F.text == "⬅️ Назад в главное меню")
async def back_to_main(message: Message, state: FSMContext):
    """Возврат в главное меню."""
    await state.clear()
    role = get_user_role(message.from_user.id)
    
    if role == ROLE_SUPERADMIN:
        await message.answer("Главное меню:", reply_markup=superadmin_main_kb())
    elif role == ROLE_MANAGER:
        await message.answer("Главное меню:", reply_markup=manager_main_kb())
    else:
        await message.answer("Главное меню:", reply_markup=employee_main_kb())


# ----------- МЕНЕДЖЕР: НАЧИСЛИТЬ ЗАРПЛАТУ -----------

@router.message(F.text == "💵 Начислить зарплату")
@require_role(ROLE_MANAGER)
async def accrual_start(message: Message, state: FSMContext):
    """Начало процесса начисления зарплаты."""
    dept_ids = get_manager_departments(message.from_user.id)
    
    if not dept_ids:
        await message.answer(
            "❌ Не найден ваш отдел. Обратитесь к директору.",
            reply_markup=manager_main_kb()
        )
        return

    employees = []
    for dept_id in dept_ids:
        employees.extend(get_department_employees(dept_id))
    
    if not employees:
        await message.answer(
            "В вашем отделе пока нет сотрудников.",
            reply_markup=manager_main_kb()
        )
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"{e['id']}: {e['full_name']}")] for e in employees],
        resize_keyboard=True,
    )
    await state.set_state(AccrualStates.waiting_for_employee)
    await message.answer("Выберите сотрудника для начисления:", reply_markup=kb)


@router.message(AccrualStates.waiting_for_employee)
@require_role(ROLE_MANAGER)
async def accrual_choose_employee(message: Message, state: FSMContext):
    """Выбор сотрудника для начисления."""
    text = message.text.strip()
    
    try:
        employee_id = int(text.split(":", 1)[0])
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Нажмите на кнопку с сотрудником.")
        return

    await state.update_data(employee_id=employee_id)
    await state.set_state(AccrualStates.waiting_for_amount)
    await message.answer(
        "Введите сумму начисления (только число):\n\n"
        "Например: <i>50000</i> или <i>50000.50</i>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


@router.message(AccrualStates.waiting_for_amount)
@require_role(ROLE_MANAGER)
async def accrual_enter_amount(message: Message, state: FSMContext):
    """Ввод суммы начисления."""
    amount = validate_amount(message.text)
    
    if amount is None:
        await message.answer(
            "❌ Неверная сумма. Введите положительное число:\n"
            "Например: 50000 или 50000.50"
        )
        return

    await state.update_data(amount=amount)
    await state.set_state(AccrualStates.waiting_for_comment)
    await message.answer(
        "Введите комментарий к начислению:\n\n"
        "Например: <i>оклад за ноябрь 2025</i>",
        parse_mode="HTML"
    )


@router.message(AccrualStates.waiting_for_comment)
@require_role(ROLE_MANAGER)
async def accrual_finish(message: Message, state: FSMContext):
    """Завершение процесса начисления."""
    data = await state.get_data()
    employee_id = data.get("employee_id")
    amount = data.get("amount")
    comment = message.text.strip()

    try:
        add_accrual(
            employee_id=employee_id,
            amount=amount,
            kind="accrual",
            comment=comment or "Начисление",
            created_by=message.from_user.id
        )
        
        await state.clear()
        await message.answer(
            f"✅ Начислено <b>{amount:.2f} ₽</b> сотруднику (ID {employee_id})\n"
            f"Комментарий: {comment}",
            reply_markup=manager_main_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при начислении: {str(e)}",
            reply_markup=manager_main_kb()
        )
        await state.clear()


# ----------- СОТРУДНИК: МОЯ ЗАРПЛАТА -----------

@router.message(F.text == "📊 Моя зарплата")
@require_role(ROLE_EMPLOYEE)
async def employee_balance(message: Message):
    """Показывает баланс сотрудника."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, full_name, position FROM employees WHERE telegram_user_id = ? AND is_active = 1",
                (message.from_user.id,),
            )
            row = cur.fetchone()

        if not row:
            await message.answer(
                "❌ Не удалось найти вас в списке сотрудников. Обратитесь к руководителю.",
                reply_markup=employee_main_kb()
            )
            return

        balance = get_employee_balance(row["id"])
        position_text = f" ({row['position']})" if row['position'] else ""
        
        await message.answer(
            f"👤 <b>Сотрудник:</b> {row['full_name']}{position_text}\n"
            f"💰 <b>Текущий баланс:</b> {balance:.2f} ₽\n\n"
            f"<i>Баланс показывает сумму начислений за вычетом выплат и авансов.</i>",
            reply_markup=employee_main_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка при получении баланса: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении данных.",
            reply_markup=employee_main_kb()
        )


# Обработчик клика по сотруднику (показ карточки)
@router.message(F.text.regexp(r"^[👤👔].+"))
async def show_employee_card(message: Message, state: FSMContext):
    """Показывает карточку сотрудника."""
    role = get_user_role(message.from_user.id)
    
    if role not in (ROLE_SUPERADMIN, ROLE_MANAGER):
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    dept_id = data.get("current_department_id")
    
    # Ищем сотрудника
    employee = get_employee_by_name(message.text, dept_id)
    
    if not employee:
        await message.answer("❌ Сотрудник не найден")
        return
    
    # Сохраняем ID сотрудника в состояние
    await state.update_data(current_employee_id=employee['id'])
    
    # Получаем данные сотрудника
    emp_id = employee['id']
    salary = get_employee_salary(emp_id)
    balance = get_employee_balance(emp_id)
    accruals = get_employee_accruals(emp_id)
    
    # Подсчитываем суммы по типам
    bonuses = sum(a['amount'] for a in accruals if a['kind'] == 'bonus')
    deductions = sum(a['amount'] for a in accruals if a['kind'] == 'deduction')
    advances = sum(a['amount'] for a in accruals if a['kind'] == 'advance')
    payouts = sum(a['amount'] for a in accruals if a['kind'] == 'payout')
    
    # Формируем текст карточки
    role_emoji = "👔" if employee['role'] == 'manager' else "👤"
    position_text = f" ({employee['position']})" if employee['position'] else ""
    
    text = f"{role_emoji} <b>{employee['full_name']}</b>{position_text}\n\n"
    text += f"💼 <b>Оклад:</b> {salary:,.2f} ₽\n"
    text += f"➕ <b>Премии:</b> {bonuses:,.2f} ₽\n"
    text += f"➖ <b>Вычеты:</b> {deductions:,.2f} ₽\n"
    text += f"💸 <b>Выданные авансы:</b> {advances:,.2f} ₽\n"
    text += f"💰 <b>Выплачено:</b> {payouts:,.2f} ₽\n"
    text += f"━━━━━━━━━━━━━━━━\n"
    text += f"💵 <b>ИТОГ К ВЫПЛАТЕ:</b> {balance:,.2f} ₽\n\n"
    
    # История начислений (последние 5)
    if accruals:
        text += "📊 <b>Последние операции:</b>\n"
        kind_emoji = {
            'salary': '💼',
            'bonus': '➕',
            'deduction': '➖',
            'advance': '💸',
            'payout': '💰'
        }
        kind_name = {
            'salary': 'Оклад',
            'bonus': 'Премия',
            'deduction': 'Вычет',
            'advance': 'Аванс',
            'payout': 'Выплата'
        }
        for a in accruals[:5]:
            emoji = kind_emoji.get(a['kind'], '•')
            name = kind_name.get(a['kind'], a['kind'])
            comment_text = f" ({a['comment']})" if a['comment'] else ""
            text += f"{emoji} {name}: {a['amount']:,.2f} ₽{comment_text}\n"
    
    # Создаём кнопки в зависимости от роли
    buttons = []
    
    if role == ROLE_SUPERADMIN:
        buttons.append([KeyboardButton(text="💸 Выдать аванс 20,000")])
        buttons.append([KeyboardButton(text="💰 Выдать зарплату")])
        buttons.append([KeyboardButton(text="👑 Назначить руководителем")])
        buttons.append([KeyboardButton(text="✏️ Изменить оклад")])
        buttons.append([KeyboardButton(text="➕ Добавить премию")])
        buttons.append([KeyboardButton(text="➖ Добавить вычет")])
    elif role == ROLE_MANAGER:
        buttons.append([KeyboardButton(text="✏️ Изменить оклад")])
        buttons.append([KeyboardButton(text="➕ Добавить премию")])
        buttons.append([KeyboardButton(text="➖ Добавить вычет")])
    
    buttons.append([KeyboardButton(text="⬅️ Назад к списку сотрудников")])
    
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# Кнопка "Назад к списку сотрудников"
@router.message(F.text == "⬅️ Назад к списку сотрудников")
async def back_to_employee_list(message: Message, state: FSMContext):
    """Возврат к списку сотрудников отдела."""
    data = await state.get_data()
    dept_id = data.get("current_department_id")
    dept_name = data.get("current_department_name")
    
    if not dept_id:
        role = get_user_role(message.from_user.id)
        kb = superadmin_main_kb() if role == ROLE_SUPERADMIN else manager_main_kb()
        await message.answer("Главное меню:", reply_markup=kb)
        return
    
    # Получаем сотрудников отдела
    employees = get_department_employees(dept_id)
    
    if not employees:
        await message.answer(
            f"<b>{dept_name}</b>\n\n<i>Нет сотрудников</i>",
            parse_mode="HTML",
            reply_markup=superadmin_main_kb()
        )
        return
    
    # Создаём кнопки
    buttons = []
    for emp in employees:
        role_badge = "👔" if emp['role'] == 'manager' else "👤"
        buttons.append([KeyboardButton(text=f"{role_badge} {emp['full_name']}")])
    
    buttons.append([KeyboardButton(text="⬅️ Назад в главное меню")])
    
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    
    await message.answer(
        f"<b>{dept_name}</b>\n\nВыберите сотрудника:",
        parse_mode="HTML",
        reply_markup=kb
    )


# Выдать аванс 20,000
@router.message(F.text == "💸 Выдать аванс 20,000")
@require_role(ROLE_SUPERADMIN)
async def give_advance(message: Message, state: FSMContext):
    """Выдача аванса 20,000 рублей."""
    data = await state.get_data()
    emp_id = data.get("current_employee_id")
    
    if not emp_id:
        await message.answer("❌ Сотрудник не выбран")
        return
    
    try:
        # Получаем текущий месяц
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        # Добавляем аванс
        add_accrual(
            employee_id=emp_id,
            amount=20000,
            kind="advance",
            comment="Аванс",
            created_by=message.from_user.id
        )
        
        # Обновляем период в записи
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE accruals SET period = ? WHERE id = (SELECT MAX(id) FROM accruals WHERE employee_id = ?)",
                (current_period, emp_id)
            )
            conn.commit()
        
        await message.answer("✅ Аванс 20,000 ₽ выдан!")
        
        # Показываем обновленную карточку
        await show_updated_card(message, state, emp_id)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при выдаче аванса: {str(e)}")


# Выдать зарплату
@router.message(F.text == "💰 Выдать зарплату")
@require_role(ROLE_SUPERADMIN)
async def give_salary(message: Message, state: FSMContext):
    """Выдача зарплаты (фиксация выплаты)."""
    data = await state.get_data()
    emp_id = data.get("current_employee_id")
    
    if not emp_id:
        await message.answer("❌ Сотрудник не выбран")
        return
    
    try:
        # Получаем текущий баланс
        balance = get_employee_balance(emp_id)
        
        if balance <= 0:
            await message.answer("❌ Нечего выплачивать (баланс ≤ 0)")
            return
        
        # Получаем текущий месяц
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        
        # Создаём запись выплаты
        add_accrual(
            employee_id=emp_id,
            amount=balance,
            kind="payout",
            comment=f"Выплата зарплаты за {current_period}",
            created_by=message.from_user.id
        )
        
        # Обновляем период
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE accruals SET period = ? WHERE id = (SELECT MAX(id) FROM accruals WHERE employee_id = ?)",
                (current_period, emp_id)
            )
            conn.commit()
        
        await message.answer(f"✅ Зарплата {balance:,.2f} ₽ выплачена!")
        
        # Показываем обновленную карточку
        await show_updated_card(message, state, emp_id)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при выплате зарплаты: {str(e)}")


# Изменить оклад
@router.message(F.text == "✏️ Изменить оклад")
async def change_salary_start(message: Message, state: FSMContext):
    """Начало изменения оклада."""
    role = get_user_role(message.from_user.id)
    
    if role not in (ROLE_SUPERADMIN, ROLE_MANAGER):
        return
    
    await state.set_state(SetSalaryStates.waiting_for_amount)
    await message.answer(
        "Введите новый оклад (число):\n\nНапример: <i>50000</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(SetSalaryStates.waiting_for_amount)
async def change_salary_finish(message: Message, state: FSMContext):
    """Завершение изменения оклада."""
    amount = validate_amount(message.text)
    
    if amount is None or amount < 0:
        await message.answer("❌ Неверная сумма. Введите положительное число:")
        return
    
    data = await state.get_data()
    emp_id = data.get("current_employee_id")
    
    if not emp_id:
        await message.answer("❌ Сотрудник не выбран")
        await state.clear()
        return
    
    try:
        set_employee_salary(emp_id, amount)
        await message.answer(f"✅ Оклад изменен на {amount:,.2f} ₽")
        await state.set_state(None)  # Очищаем только состояние FSM, но не data
        await show_updated_card(message, state, emp_id)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()


# Добавить премию
@router.message(F.text == "➕ Добавить премию")
async def add_bonus_start(message: Message, state: FSMContext):
    """Начало добавления премии."""
    role = get_user_role(message.from_user.id)
    
    if role not in (ROLE_SUPERADMIN, ROLE_MANAGER):
        return
    
    await state.set_state(AddBonusStates.waiting_for_amount)
    await message.answer(
        "Введите сумму премии:\n\nНапример: <i>10000</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(AddBonusStates.waiting_for_amount)
async def add_bonus_comment(message: Message, state: FSMContext):
    """Ввод комментария к премии."""
    amount = validate_amount(message.text)
    
    if amount is None or amount <= 0:
        await message.answer("❌ Неверная сумма. Введите положительное число:")
        return
    
    await state.update_data(bonus_amount=amount)
    await state.set_state(AddBonusStates.waiting_for_comment)
    await message.answer("Введите комментарий к премии:\n\nНапример: <i>За выполнение плана</i>", parse_mode="HTML")


@router.message(AddBonusStates.waiting_for_comment)
async def add_bonus_finish(message: Message, state: FSMContext):
    """Завершение добавления премии."""
    data = await state.get_data()
    emp_id = data.get("current_employee_id")
    amount = data.get("bonus_amount")
    comment = message.text.strip()
    
    if not emp_id or not amount:
        await message.answer("❌ Ошибка данных")
        await state.clear()
        return
    
    try:
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        add_accrual(
            employee_id=emp_id,
            amount=amount,
            kind="bonus",
            comment=comment or "Премия",
            created_by=message.from_user.id
        )
        
        # Обновляем период
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE accruals SET period = ? WHERE id = (SELECT MAX(id) FROM accruals WHERE employee_id = ?)",
                (current_period, emp_id)
            )
            conn.commit()
        
        await message.answer(f"✅ Премия {amount:,.2f} ₽ добавлена!")
        await state.set_state(None)
        await show_updated_card(message, state, emp_id)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()


# Добавить вычет
@router.message(F.text == "➖ Добавить вычет")
async def add_deduction_start(message: Message, state: FSMContext):
    """Начало добавления вычета."""
    role = get_user_role(message.from_user.id)
    
    if role not in (ROLE_SUPERADMIN, ROLE_MANAGER):
        return
    
    await state.set_state(AddDeductionStates.waiting_for_amount)
    await message.answer(
        "Введите сумму вычета (штрафа):\n\nНапример: <i>5000</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(AddDeductionStates.waiting_for_amount)
async def add_deduction_comment(message: Message, state: FSMContext):
    """Ввод комментария к вычету."""
    amount = validate_amount(message.text)
    
    if amount is None or amount <= 0:
        await message.answer("❌ Неверная сумма. Введите положительное число:")
        return
    
    await state.update_data(deduction_amount=amount)
    await state.set_state(AddDeductionStates.waiting_for_comment)
    await message.answer("Введите причину вычета:\n\nНапример: <i>Опоздание</i>", parse_mode="HTML")


@router.message(AddDeductionStates.waiting_for_comment)
async def add_deduction_finish(message: Message, state: FSMContext):
    """Завершение добавления вычета."""
    data = await state.get_data()
    emp_id = data.get("current_employee_id")
    amount = data.get("deduction_amount")
    comment = message.text.strip()
    
    if not emp_id or not amount:
        await message.answer("❌ Ошибка данных")
        await state.clear()
        return
    
    try:
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        add_accrual(
            employee_id=emp_id,
            amount=amount,
            kind="deduction",
            comment=comment or "Вычет",
            created_by=message.from_user.id
        )
        
        # Обновляем период
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE accruals SET period = ? WHERE id = (SELECT MAX(id) FROM accruals WHERE employee_id = ?)",
                (current_period, emp_id)
            )
            conn.commit()
        
        await message.answer(f"✅ Вычет {amount:,.2f} ₽ добавлен!")
        await state.set_state(None)
        await show_updated_card(message, state, emp_id)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()


# Вспомогательная функция для показа обновлённой карточки
async def show_updated_card(message: Message, state: FSMContext, emp_id: int):
    """Показывает обновлённую карточку сотрудника."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))
            employee = cur.fetchone()
        
        if not employee:
            return
        
        salary = get_employee_salary(emp_id)
        balance = get_employee_balance(emp_id)
        accruals = get_employee_accruals(emp_id)
        
        bonuses = sum(a['amount'] for a in accruals if a['kind'] == 'bonus')
        deductions = sum(a['amount'] for a in accruals if a['kind'] == 'deduction')
        advances = sum(a['amount'] for a in accruals if a['kind'] == 'advance')
        payouts = sum(a['amount'] for a in accruals if a['kind'] == 'payout')
        
        role_emoji = "👔" if employee['role'] == 'manager' else "👤"
        position_text = f" ({employee['position']})" if employee['position'] else ""
        
        text = f"{role_emoji} <b>{employee['full_name']}</b>{position_text}\n\n"
        text += f"💼 <b>Оклад:</b> {salary:,.2f} ₽\n"
        text += f"➕ <b>Премии:</b> {bonuses:,.2f} ₽\n"
        text += f"➖ <b>Вычеты:</b> {deductions:,.2f} ₽\n"
        text += f"💸 <b>Выданные авансы:</b> {advances:,.2f} ₽\n"
        text += f"💰 <b>Выплачено:</b> {payouts:,.2f} ₽\n"
        text += f"━━━━━━━━━━━━━━━━\n"
        text += f"💵 <b>ИТОГ К ВЫПЛАТЕ:</b> {balance:,.2f} ₽\n\n"
        
        if accruals:
            text += "📊 <b>Последние операции:</b>\n"
            kind_emoji = {
                'salary': '💼',
                'bonus': '➕',
                'deduction': '➖',
                'advance': '💸',
                'payout': '💰'
            }
            kind_name = {
                'salary': 'Оклад',
                'bonus': 'Премия',
                'deduction': 'Вычет',
                'advance': 'Аванс',
                'payout': 'Выплата'
            }
            for a in accruals[:5]:
                emoji = kind_emoji.get(a['kind'], '•')
                name = kind_name.get(a['kind'], a['kind'])
                comment_text = f" ({a['comment']})" if a['comment'] else ""
                text += f"{emoji} {name}: {a['amount']:,.2f} ₽{comment_text}\n"
        
        role = get_user_role(message.from_user.id)
        buttons = []
        
        if role == ROLE_SUPERADMIN:
            buttons.append([KeyboardButton(text="💸 Выдать аванс 20,000")])
            buttons.append([KeyboardButton(text="💰 Выдать зарплату")])
            buttons.append([KeyboardButton(text="👑 Назначить руководителем")])
            buttons.append([KeyboardButton(text="✏️ Изменить оклад")])
            buttons.append([KeyboardButton(text="➕ Добавить премию")])
            buttons.append([KeyboardButton(text="➖ Добавить вычет")])
        elif role == ROLE_MANAGER:
            buttons.append([KeyboardButton(text="✏️ Изменить оклад")])
            buttons.append([KeyboardButton(text="➕ Добавить премию")])
            buttons.append([KeyboardButton(text="➖ Добавить вычет")])
        
        buttons.append([KeyboardButton(text="⬅️ Назад к списку сотрудников")])
        
        kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        
    except Exception as e:
        logging.error(f"Ошибка при показе обновленной карточки: {e}")


# ---------------- ЗАПУСК БОТА ----------------

async def main():
    """Главная функция запуска бота."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Инициализируем БД
    init_db()
    
    # Импортируем структуру компании
    import_company_structure()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    logging.info("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
