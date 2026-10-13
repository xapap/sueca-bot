import asyncio
import logging
import os
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TOKEN = os.getenv("TELEGRAM_TOKEN")

NAIPES = ["♠️", "♥️", "♦️", "♣️"]
FIGURAS = ["A", "7", "K", "J", "Q", "6", "5", "4", "3", "2"]
PONTOS = {"A": 11, "7": 10, "K": 4, "J": 3, "Q": 2}


class JogoSueca:

  def __init__(self, chat_id, jogadores_iniciais):
    self.chat_id = chat_id
    self.jogadores = list(jogadores_iniciais)

    # Preencher vagas com bots até termos 4 lugares
    bot_num = 1
    while len(self.jogadores) < 4:
      self.jogadores.append((f"bot_{bot_num}", f"🤖 Bot {bot_num}"))
      bot_num += 1

    self.pontos_equipa = {1: 0, 2: 0}

    # Baralhar e dar 10 cartas a cada jogador
    baralho = [(v, n) for n in NAIPES for v in FIGURAS]
    random.shuffle(baralho)

    self.trunfo_carta = baralho[-1]
    self.trunfo = self.trunfo_carta[1]

    self.maos = {
        self.jogadores[0][0]: sorted(
            baralho[0:10], key=lambda c: (c[1], FIGURAS.index(c[0]))
        ),
        self.jogadores[1][0]: sorted(
            baralho[10:20], key=lambda c: (c[1], FIGURAS.index(c[0]))
        ),
        self.jogadores[2][0]: sorted(
            baralho[20:30], key=lambda c: (c[1], FIGURAS.index(c[0]))
        ),
        self.jogadores[3][0]: sorted(
            baralho[30:40], key=lambda c: (c[1], FIGURAS.index(c[0]))
        ),
    }

    self.turno_atual = 0
    self.vaza_atual = []
    self.vazas_jogadas = 0

  def jogador_atual(self):
    return self.jogadores[self.turno_atual]

  def cartas_validas(self, user_id):
    mao = self.maos[user_id]
    if not self.vaza_atual:
      return mao
    naipe_saida = self.vaza_atual[0][1][1]
    do_naipe = [c for c in mao if c[1] == naipe_saida]
    return do_naipe if do_naipe else mao

  def resolver_vaza(self):
    naipe_saida = self.vaza_atual[0][1][1]

    def peso(item):
      _, (val, naipe) = item
      p = 10 - FIGURAS.index(val)
      if naipe == self.trunfo:
        return 200 + p
      if naipe == naipe_saida:
        return 100 + p
      return 0

    vencedor_id, _ = max(self.vaza_atual, key=peso)
    pts = sum(PONTOS.get(c[0], 0) for _, c in self.vaza_atual)

    idx_vencedor = [j[0] for j in self.jogadores].index(vencedor_id)
    equipa = 1 if idx_vencedor in [0, 2] else 2
    self.pontos_equipa[equipa] += pts

    self.turno_atual = idx_vencedor
    self.vaza_atual = []
    self.vazas_jogadas += 1
    return vencedor_id, pts


jogos_ativos = {}
lobbies = {}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text(
      "🃏 **Bem-vindo à Sueca!**\n\n"
      "Comandos:\n"
      "• `/jogar` — Iniciar uma mesa\n"
      "• `/cancelar` — Fechar a partida atual\n\n"
      "Podes jogar sozinho contra 3 bots ou convidar amigos!",
      parse_mode="Markdown",
  )


async def cmd_jogar(update: Update, context: ContextTypes.DEFAULT_TYPE):
  chat_id = update.effective_chat.id
  user = update.effective_user

  if chat_id in jogos_ativos:
    await update.message.reply_text(
        "Já há uma partida a decorrer aqui! Usa `/cancelar` se quiseres parar."
    )
    return

  lobbies[chat_id] = [(user.id, user.first_name)]
  keyboard = [
      [InlineKeyboardButton("➕ Entrar na Mesa", callback_data="entrar_mesa")],
      [
          InlineKeyboardButton(
              "🚀 Começar Agora (Com Bots)", callback_data="arrancar_mesa"
          )
      ],
  ]

  await update.message.reply_text(
      f"🃏 **Mesa Aberta!**\n\n"
      f"Jogadores (1/4):\n1. {user.first_name}\n\n"
      f"Aguarda por amigos ou clica em **Começar Agora** para preencher com robôs:",
      reply_markup=InlineKeyboardMarkup(keyboard),
      parse_mode="Markdown",
  )


async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
  chat_id = update.effective_chat.id
  if chat_id in jogos_ativos:
    del jogos_ativos[chat_id]
    await update.message.reply_text("Partida cancelada com sucesso.")
  elif chat_id in lobbies:
    del lobbies[chat_id]
    await update.message.reply_text("Mesa cancelada.")
  else:
    await update.message.reply_text("Não há nenhuma mesa ou partida ativa aqui.")


async def callback_mesa(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  chat_id = query.message.chat.id
  user = query.from_user

  if chat_id not in lobbies:
    return

  mesa = lobbies[chat_id]

  if query.data == "entrar_mesa":
    if any(u[0] == user.id for u in mesa):
      await query.answer("Já estás inscrito na mesa!", show_alert=True)
      return

    mesa.append((user.id, user.first_name))
    if len(mesa) == 4:
      await arrancar_jogo(chat_id, mesa, query, context)
      return

    nomes = "\n".join([f"{i+1}. {u[1]}" for i, u in enumerate(mesa)])
    keyboard = [
        [InlineKeyboardButton("➕ Entrar na Mesa", callback_data="entrar_mesa")],
        [
            InlineKeyboardButton(
                "🚀 Começar Agora (Com Bots)", callback_data="arrancar_mesa"
            )
        ],
    ]
    await query.edit_message_text(
        f"🃏 **Mesa Aberta!**\n\n"
        f"Jogadores ({len(mesa)}/4):\n{nomes}\n\n"
        f"Cliquem para entrar ou comecem com bots:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

  elif query.data == "arrancar_mesa":
    await arrancar_jogo(chat_id, mesa, query, context)


async def arrancar_jogo(chat_id, jogadores, query, context):
  jogo = JogoSueca(chat_id, jogadores)
  jogos_ativos[chat_id] = jogo
  if chat_id in lobbies:
    del lobbies[chat_id]

  eq1 = f"{jogo.jogadores[0][1]} e {jogo.jogadores[2][1]}"
  eq2 = f"{jogo.jogadores[1][1]} e {jogo.jogadores[3][1]}"

  await query.edit_message_text(
      f"🎮 **Partida Iniciada!**\n\n"
      f"🔹 Equipa 1: {eq1}\n"
      f"🔸 Equipa 2: {eq2}\n\n"
      f"🎴 **Trunfo:** {jogo.trunfo_carta[0]}{jogo.trunfo_carta[1]}\n"
      f"Primeiro a jogar: **{jogo.jogador_atual()[1]}**!",
      parse_mode="Markdown",
  )
  await processar_jogada(context, jogo)


async def processar_jogada(context: ContextTypes.DEFAULT_TYPE, jogo: JogoSueca):
  user_id, nome = jogo.jogador_atual()

  # Se for Bot
  if str(user_id).startswith("bot_"):
    await asyncio.sleep(1.2)
    cartas = jogo.cartas_validas(user_id)
    jogada = random.choice(cartas)
    await finalizar_jogada(context, jogo, user_id, jogada)
  else:
    # Se for Jogador Humano
    cartas = jogo.cartas_validas(user_id)
    botoes, linha = [], []
    for val, naipe in cartas:
      linha.append(
          InlineKeyboardButton(
              f"{val}{naipe}", callback_data=f"j_{val}_{naipe}"
          )
      )
      if len(linha) == 4:
        botoes.append(linha)
        linha = []
    if linha:
      botoes.append(linha)

    await context.bot.send_message(
        chat_id=jogo.chat_id,
        text=f"👉 Vez de: **{nome}** (Trunfo: {jogo.trunfo})\nEscolhe a tua carta:",
        reply_markup=InlineKeyboardMarkup(botoes),
        parse_mode="Markdown",
    )


async def callback_jogar_carta(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
  query = update.callback_query
  await query.answer()
  chat_id = query.message.chat.id
  user_id = query.from_user.id

  jogo = jogos_ativos.get(chat_id)
  if not jogo:
    return

  if jogo.jogador_atual()[0] != user_id:
    await query.answer("Não é a tua vez de jogar!", show_alert=True)
    return

  _, val, naipe = query.data.split("_")
  carta = (val, naipe)

  await query.edit_message_reply_markup(reply_markup=None)
  await finalizar_jogada(context, jogo, user_id, carta)


async def finalizar_jogada(
    context: ContextTypes.DEFAULT_TYPE, jogo: JogoSueca, user_id, carta
):
  jogo.maos[user_id].remove(carta)
  jogo.vaza_atual.append((user_id, carta))

  nome = next(u[1] for u in jogo.jogadores if u[0] == user_id)
  mesa_str = " ".join([f"{c[0]}{c[1]}" for _, c in jogo.vaza_atual])

  await context.bot.send_message(
      chat_id=jogo.chat_id,
      text=f"{nome} jogou: **{carta[0]}{carta[1]}**\n🃏 Na mesa: {mesa_str}",
      parse_mode="Markdown",
  )

  if len(jogo.vaza_atual) == 4:
    vencedor_id, pts = jogo.resolver_vaza()
    vencedor_nome = next(u[1] for u in jogo.jogadores if u[0] == vencedor_id)

    await context.bot.send_message(
        chat_id=jogo.chat_id,
        text=f"🏆 **{vencedor_nome}** fez a vaza (+{pts} pts)!",
        parse_mode="Markdown",
    )

    if jogo.vazas_jogadas == 10:
      p1, p2 = jogo.pontos_equipa[1], jogo.pontos_equipa[2]
      res = f"🏁 **Fim do Jogo!**\n\n🔹 Equipa 1: {p1} pts\n🔸 Equipa 2: {p2} pts\n\n"
      if p1 > 60:
        res += "🎉 Vitória da **Equipa 1**!"
      elif p2 > 60:
        res += "🎉 Vitória da **Equipa 2**!"
      else:
        res += "🤝 Empate a 60 pontos!"
      await context.bot.send_message(
          chat_id=jogo.chat_id, text=res, parse_mode="Markdown"
      )
      del jogos_ativos[jogo.chat_id]
      return
  else:
    jogo.turno_atual = (jogo.turno_atual + 1) % 4

  await processar_jogada(context, jogo)


def main():
  app = Application.builder().token(TOKEN).build()
  app.add_handler(CommandHandler("start", cmd_start))
  app.add_handler(CommandHandler("jogar", cmd_jogar))
  app.add_handler(CommandHandler("cancelar", cmd_cancelar))
  app.add_handler(
      CallbackQueryHandler(
          callback_mesa, pattern="^(entrar_mesa|arrancar_mesa)$"
      )
  )
  app.add_handler(CallbackQueryHandler(callback_jogar_carta, pattern="^j_"))

  print("Bot de Sueca a correr...")
  app.run_polling()


if __name__ == "__main__":
  main()
