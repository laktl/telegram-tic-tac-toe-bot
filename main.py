import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение токена из переменных окружения
API_TOKEN = os.getenv('BOT_TOKEN')

if not API_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Хранилища ---
games = {}
user_games = {}


# --- Вспомогательные функции ---
def render_board(board):
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            cell = board[i + j]
            symbol = cell if cell != " " else "⬜"
            row.append(InlineKeyboardButton(text=symbol, callback_data=f"move_{i + j}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def check_winner(board):
    wins = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],
        [0, 3, 6], [1, 4, 7], [2, 5, 8],
        [0, 4, 8], [2, 4, 6]
    ]
    for a, b, c in wins:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    if " " not in board:
        return "draw"
    return None


# --- Команды ---
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Привет! Используй /newgame чтобы создать игру или /join <id> чтобы присоединиться")


@dp.message(Command("newgame"))
async def new_game(message: Message):
    user_id = message.from_user.id
    if user_id in user_games:
        await message.answer("Ты уже участвуешь в игре!")
        return

    game_id = str(user_id)
    games[game_id] = {
        "board": [" "] * 9,
        "players": [user_id, None],
        "turn": 0,
        "chat_id": message.chat.id,
        "message_id": None,
        "player2_message_id": None
    }
    user_games[user_id] = game_id

    msg = await message.answer(
        f"Игра создана! ID игры: {game_id}\nЖдем второго игрока...\nТы играешь ❌",
        reply_markup=render_board(games[game_id]["board"])
    )
    games[game_id]["message_id"] = msg.message_id


@dp.message(Command("join"))
async def join_game(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Укажи ID игры: /join <id>")
        return

    game_id = args[1]
    if game_id not in games:
        await message.answer("Такой игры нет.")
        return

    game = games[game_id]
    if game["players"][1] is not None:
        await message.answer("Эта игра уже заполнена.")
        return

    user_id = message.from_user.id
    if user_id in user_games:
        await message.answer("Ты уже участвуешь в другой игре!")
        return

    game["players"][1] = user_id
    user_games[user_id] = game_id

    text = f"Игра началась!\nИгрок 1 (❌): {game['players'][0]}\nИгрок 2 (⭕): {game['players'][1]}\n\nХодит Игрок 1 (❌)"
    await bot.edit_message_text(
        chat_id=game["chat_id"],
        message_id=game["message_id"],
        text=text,
        reply_markup=render_board(game["board"])
    )

    player2_msg = await message.answer(
        f"Ты присоединился к игре!\nТы играешь ⭕\n\nХодит Игрок 1 (❌)",
        reply_markup=render_board(game["board"])
    )
    game["player2_message_id"] = player2_msg.message_id
    game["player2_chat_id"] = message.chat.id


@dp.callback_query(F.data.startswith("move_"))
async def handle_move(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_games:
        await callback.answer("Ты не в игре!")
        return

    game_id = user_games[user_id]
    game = games.get(game_id)
    if not game or user_id not in game["players"]:
        await callback.answer("Ты не участвуешь в этой игре!")
        return

    board = game["board"]
    turn = game["turn"]
    current_player = game["players"][turn]
    if user_id != current_player:
        await callback.answer("Сейчас не твой ход!")
        return

    idx = int(callback.data.split("_")[1])
    if board[idx] != " ":
        await callback.answer("Клетка занята!")
        return

    mark = "❌" if turn == 0 else "⭕"
    board[idx] = mark

    winner = check_winner(board)
    if winner:
        if winner == "draw":
            text = "Ничья 🤝"
        else:
            winner_id = game["players"][0] if winner == "❌" else game["players"][1]
            text = f"Победил игрок {winner_id} ({winner}) 🎉"

        await bot.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["message_id"],
            text=text,
            reply_markup=render_board(board)
        )
        if game.get("player2_message_id"):
            await bot.edit_message_text(
                chat_id=game["player2_chat_id"],
                message_id=game["player2_message_id"],
                text=text,
                reply_markup=render_board(board)
            )

        for pid in game["players"]:
            if pid:
                user_games.pop(pid, None)
        games.pop(game_id, None)
        await callback.answer()
        return

    game["turn"] = 1 - turn
    next_player_id = game["players"][game["turn"]]
    next_symbol = "❌" if game["turn"] == 0 else "⭕"
    next_text = f"Ходит игрок {next_player_id} ({next_symbol})"

    await bot.edit_message_text(
        chat_id=game["chat_id"],
        message_id=game["message_id"],
        text=next_text,
        reply_markup=render_board(board)
    )
    if game.get("player2_message_id"):
        await bot.edit_message_text(
            chat_id=game["player2_chat_id"],
            message_id=game["player2_message_id"],
            text=next_text,
            reply_markup=render_board(board)
        )

    await callback.answer()


# --- Запуск бота ---
async def main():
    logger.info("Бот запущен!")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())