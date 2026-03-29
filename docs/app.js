const API_BASE = (window.LAOBAN_API_BASE || '').replace(/\/$/, '');
const BOT_THINK_MS = 190;

const RANK_LABELS = {11: 'J', 12: 'Q', 13: 'K', 14: 'A', 17: '2', 20: 'SJ', 30: 'BJ'};
const SUIT_SYMBOLS = {H: '♥', D: '♦', C: '♣', S: '♠'};
const PIP_LAYOUTS = {
  1: [[50, 50, 0]],
  2: [[50, 29, 0], [50, 71, 180]],
  3: [[50, 24, 0], [50, 50, 0], [50, 76, 180]],
  4: [[35, 30, 0], [65, 30, 0], [35, 70, 180], [65, 70, 180]],
  5: [[35, 28, 0], [65, 28, 0], [50, 50, 0], [35, 72, 180], [65, 72, 180]],
  6: [[35, 25, 0], [65, 25, 0], [35, 50, 0], [65, 50, 0], [35, 75, 180], [65, 75, 180]],
  7: [[35, 22, 0], [65, 22, 0], [50, 38, 0], [35, 50, 0], [65, 50, 0], [35, 76, 180], [65, 76, 180]],
  8: [[35, 20, 0], [65, 20, 0], [35, 37, 0], [65, 37, 0], [35, 63, 180], [65, 63, 180], [35, 80, 180], [65, 80, 180]],
  9: [[35, 18, 0], [65, 18, 0], [35, 34, 0], [65, 34, 0], [50, 50, 0], [35, 66, 180], [65, 66, 180], [35, 82, 180], [65, 82, 180]],
  10: [[34, 22, 0], [66, 22, 0], [34, 36, 0], [66, 36, 0], [34, 50, 0], [66, 50, 0], [34, 64, 180], [66, 64, 180], [34, 78, 180], [66, 78, 180]],
};

const state = {
  sessionId: null,
  payload: null,
  selectedCardKeys: [],
  pendingBotTimeout: null,
  requestInFlight: false,
};

const els = {
  meta: document.getElementById('meta'),
  status: document.getElementById('status'),
  turn: document.getElementById('turn'),
  wins: document.getElementById('wins'),
  deckSize: document.getElementById('deck-size'),
  opponentStatus: document.getElementById('opponent-status'),
  lastMove: document.getElementById('last-move'),
  result: document.getElementById('result'),
  selection: document.getElementById('selection'),
  humanHand: document.getElementById('human-hand'),
  opponentHand: document.getElementById('opponent-hand'),
  tableCards: document.getElementById('table-cards'),
  moves: document.getElementById('moves'),
  log: document.getElementById('log'),
  playBtn: document.getElementById('play-btn'),
  passBtn: document.getElementById('pass-btn'),
  clearBtn: document.getElementById('clear-btn'),
  newGameBtn: document.getElementById('new-game-btn'),
  startingPlayer: document.getElementById('starting-player'),
  deckCards: document.querySelector('.deck-cards'),
};

function endpoint(path) {
  return `${API_BASE}${path}`;
}

function rankText(rank) {
  return RANK_LABELS[rank] || String(rank);
}

function suitSymbol(suit) {
  return SUIT_SYMBOLS[suit] || '';
}

function suitColor(card) {
  return card.color || ((card.suit === 'H' || card.suit === 'D') ? 'red' : 'black');
}

function currentScores(payload) {
  const scores = payload.scores || payload.score || {};
  return {
    you: scores.you ?? 0,
    bot: scores.bot ?? 0,
    pot: scores.pot ?? payload.pot ?? 0,
  };
}

function actionCardKeys(action) {
  return (action.cards || []).map((c) => c.key).sort();
}

function sameKeys(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function selectedAction() {
  if (!state.payload || !state.selectedCardKeys.length) return null;
  const selected = [...state.selectedCardKeys].sort();
  return (state.payload.legal_actions || []).find(
    (action) => !action.is_pass && sameKeys(actionCardKeys(action), selected)
  ) || null;
}

function selectedMoveText() {
  const action = selectedAction();
  if (action) return action.label;
  if (!state.selectedCardKeys.length) return 'No cards selected.';
  return 'Selected cards do not form a legal move.';
}

function displayCard(rawCard) {
  return {
    ...rawCard,
    rankLabel: rawCard.rank_label || rankText(rawCard.rank),
    suitText: rawCard.suit_symbol || suitSymbol(rawCard.suit),
    colorClass: suitColor(rawCard),
  };
}

function pipLayoutForRank(rank) {
  if (rank >= 3 && rank <= 10) return PIP_LAYOUTS[rank];
  if (rank === 14) return PIP_LAYOUTS[1];
  if (rank === 17) return PIP_LAYOUTS[2];
  return PIP_LAYOUTS[1];
}

function pipMarkup(rawCard) {
  const card = displayCard(rawCard);
  const layout = pipLayoutForRank(card.rank);
  return `
    <div class="pip-grid ${card.colorClass}">
      ${layout.map(([x, y, angle]) => `
        <span class="pip${angle ? ' flipped' : ''}" style="left:${x}%; top:${y}%">${card.suitText}</span>
      `).join('')}
    </div>
  `;
}

function faceMarkup(rawCard) {
  const card = displayCard(rawCard);
  const emblem = card.rank === 11 ? '♞' : card.rank === 12 ? '♛' : '♚';
  const jewel = card.rank === 11
    ? '<span class="jewel diamond"></span>'
    : card.rank === 12
      ? '<span class="jewel orb"></span>'
      : '<span class="jewel crown"></span>';
  return `
    <div class="art-frame face-frame ${card.colorClass}">
      <div class="frame-rule top"></div>
      <div class="frame-rule bottom"></div>
      <div class="frame-wing left"></div>
      <div class="frame-wing right"></div>
      <div class="frame-suit top">${card.suitText}</div>
      <div class="frame-emblem">${emblem}</div>
      <div class="frame-jewel">${jewel}</div>
      <div class="frame-suit bottom">${card.suitText}</div>
    </div>
  `;
}

function jokerMarkup(rawCard) {
  const card = displayCard(rawCard);
  const small = card.rank === 20;
  return `
    <div class="art-frame joker-frame ${small ? 'small' : 'big'}">
      <div class="frame-rule top"></div>
      <div class="frame-rule bottom"></div>
      <div class="frame-wing left"></div>
      <div class="frame-wing right"></div>
      <div class="frame-word top">JOKER</div>
      <div class="joker-emblem-wrap">
        <div class="joker-halo"></div>
        <div class="joker-emblem">${small ? '✦' : '✹'}</div>
        <div class="joker-jewel ${small ? 'diamond' : 'orb'}"></div>
      </div>
      <div class="frame-word bottom">${small ? 'SMALL' : 'BIG'}</div>
    </div>
  `;
}

function cardCenterMarkup(rawCard) {
  const card = displayCard(rawCard);
  if (card.rank === 20 || card.rank === 30) return jokerMarkup(card);
  if ([11, 12, 13].includes(card.rank)) return faceMarkup(card);
  return pipMarkup(card);
}

function faceDownMarkup() {
  return `
    <div class="card-shadow"></div>
    <div class="card-back-outer">
      <div class="card-back-inner">
        <div class="back-bar left"></div>
        <div class="back-bar center"></div>
        <div class="back-bar right"></div>
        <div class="back-badge top">♠ ♥ ♣ ♦</div>
        <div class="back-badge bottom">5 · 10 · K</div>
      </div>
    </div>
  `;
}

function createFaceDownCard() {
  const el = document.createElement('div');
  el.className = 'card-shell back';
  el.innerHTML = faceDownMarkup();
  return el;
}

function createCardElement(rawCard, options = {}) {
  const clickable = !!options.clickable;
  const playable = !!options.playable;
  const selected = !!options.selected;
  const card = displayCard(rawCard);

  const wrapper = document.createElement('div');
  wrapper.className = [
    'card-shell',
    'face-up',
    card.colorClass,
    clickable ? 'clickable' : '',
    playable ? 'playable' : '',
    selected ? 'selected' : '',
  ].filter(Boolean).join(' ');

  const topIcon = card.suitText || '★';
  wrapper.innerHTML = `
    <div class="card-shadow"></div>
    <div class="card-outer">
      <div class="card-inner">
        <div class="corner top ${card.colorClass}">
          <div class="rank">${card.rankLabel}</div>
          <div class="suit">${topIcon}</div>
        </div>
        <div class="card-center ${card.colorClass}">${cardCenterMarkup(card)}</div>
        <div class="corner bottom ${card.colorClass}">
          <div class="rank">${card.rankLabel}</div>
          <div class="suit">${topIcon}</div>
        </div>
      </div>
    </div>
  `;

  if (clickable && options.onClick) {
    wrapper.addEventListener('click', options.onClick);
  }
  return wrapper;
}

function renderStaticDrawPile() {
  if (!els.deckCards) return;
  els.deckCards.innerHTML = '';
  for (const cls of ['offset-a', 'offset-b', 'offset-c']) {
    const card = createFaceDownCard();
    card.classList.add(cls, 'static-draw-card');
    els.deckCards.appendChild(card);
  }
}

function clearBotDelay() {
  if (state.pendingBotTimeout) {
    clearTimeout(state.pendingBotTimeout);
    state.pendingBotTimeout = null;
  }
}

async function api(path, body, method = 'POST') {
  const res = await fetch(endpoint(path), {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: method === 'GET' ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

function applyPayload(payload) {
  state.payload = payload;
  state.sessionId = payload.session_id || payload.game_id || state.sessionId;
}

function renderMoves(payload) {
  els.moves.innerHTML = '';
  const legalActions = payload.legal_actions || [];
  if (!legalActions.length) {
    const move = document.createElement('div');
    move.className = 'move disabled';
    move.textContent = payload.done ? 'Game over' : (payload.pending_bot_turn ? 'Bot is thinking…' : 'Waiting for bot…');
    els.moves.appendChild(move);
    return;
  }

  for (const action of legalActions) {
    const move = document.createElement('div');
    move.className = `move${action.is_pass ? ' pass' : ''}`;
    const actionMatch = selectedAction();
    if (actionMatch && action.index === actionMatch.index) move.classList.add('selected');
    move.textContent = action.label;
    move.addEventListener('click', () => {
      state.selectedCardKeys = action.is_pass ? [] : action.cards.map((card) => card.key);
      render();
    });
    move.addEventListener('dblclick', () => playAction(action.index));
    els.moves.appendChild(move);
  }
}

function blurControls() {
  if (document.activeElement && typeof document.activeElement.blur === 'function') {
    document.activeElement.blur();
  }
}

function render() {
  const payload = state.payload;
  if (!payload) return;

  renderStaticDrawPile();

  const scores = currentScores(payload);
  const playableKeys = new Set(payload.playable_card_keys || []);
  els.status.textContent = `You ${scores.you} · Bot ${scores.bot} · Pot ${scores.pot}`;
  const turnLabel = payload.turn === 'you' ? 'You' : payload.turn === 'bot' ? 'Bot' : 'Game Over';
  els.turn.textContent = `Turn: ${turnLabel} · Hand type: ${payload.hand_type || 'open'}`;
  els.wins.textContent = `Wins - You: ${payload.wins?.you ?? 0} · Bot: ${payload.wins?.bot ?? 0}`;
  els.deckSize.textContent = `${payload.deck_size} card${payload.deck_size === 1 ? '' : 's'}`;
  els.opponentStatus.textContent = `Cards in hand: ${payload.opponent_card_count}`;
  els.lastMove.textContent = `Last move: ${payload.last_move ? payload.last_move.label : 'None'}`;
  els.result.textContent = payload.result || '';
  els.selection.textContent = payload.pending_bot_turn ? 'Bot is thinking…' : selectedMoveText();
  els.log.textContent = (payload.log || []).join('\n');

  els.humanHand.innerHTML = '';
  for (const rawCard of payload.human_hand || []) {
    const card = displayCard(rawCard);
    const playable = playableKeys.has(card.key);
    els.humanHand.appendChild(createCardElement(card, {
      clickable: payload.turn === 'you' && !payload.done && !state.requestInFlight && playable,
      playable,
      selected: playable && state.selectedCardKeys.includes(card.key),
      onClick: () => toggleCard(card.key),
    }));
  }

  els.opponentHand.innerHTML = '';
  for (let i = 0; i < (payload.opponent_card_count || 0); i += 1) {
    els.opponentHand.appendChild(createFaceDownCard());
  }

  els.tableCards.innerHTML = '';
  els.tableCards.classList.toggle('empty-state', !(payload.last_move && !payload.last_move.is_pass));
  if (payload.last_move && !payload.last_move.is_pass) {
    const typeLabel = document.createElement('div');
    typeLabel.className = 'table-type';
    typeLabel.textContent = payload.last_move.type.toUpperCase();
    els.tableCards.appendChild(typeLabel);
    const row = document.createElement('div');
    row.className = 'card-row table-play-row';
    for (const card of payload.last_move.cards) {
      row.appendChild(createCardElement(card));
    }
    els.tableCards.appendChild(row);
  } else {
    els.tableCards.textContent = 'No active table move';
  }

  renderMoves(payload);

  const canAct = payload.turn === 'you' && !payload.done && !state.requestInFlight;
  const canPass = canAct && (payload.legal_actions || []).some((action) => action.is_pass);
  const canPlay = canAct && !!selectedAction();
  els.playBtn.disabled = !canPlay;
  els.passBtn.disabled = !canPass;
  els.clearBtn.disabled = state.selectedCardKeys.length === 0 || state.requestInFlight;
  els.newGameBtn.disabled = state.requestInFlight;
  els.startingPlayer.disabled = state.requestInFlight;
}

function toggleCard(key) {
  const payload = state.payload;
  if (!payload || payload.turn !== 'you' || payload.done || state.requestInFlight) return;
  const playable = new Set(payload.playable_card_keys || []);
  if (!playable.has(key)) return;
  if (state.selectedCardKeys.includes(key)) {
    state.selectedCardKeys = state.selectedCardKeys.filter((k) => k !== key);
  } else {
    state.selectedCardKeys = [...state.selectedCardKeys, key];
  }
  render();
}

async function loadHealth() {
  try {
    const res = await fetch(endpoint('/health'));
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Health check failed');
    els.meta.textContent = `Connected to ${API_BASE || 'same-origin API'} | encoder: ${data.encoder} | dims: ${data.state_dim}/${data.action_dim} | checkpoint: ${data.checkpoint}`;
  } catch (err) {
    els.meta.innerHTML = `<span class="error">Backend connection failed.</span> Check <code>config.js</code>.`;
    throw err;
  }
}

async function startNewGame() {
  clearBotDelay();
  blurControls();
  state.requestInFlight = true;
  render();
  try {
    const botFirst = els.startingPlayer.value === 'bot';
    const payload = state.sessionId
      ? await api('/api/reset', { session_id: state.sessionId, bot_first: botFirst })
      : await api('/api/new-game', { bot_first: botFirst });
    state.selectedCardKeys = [];
    applyPayload(payload);
    render();
  } finally {
    state.requestInFlight = false;
    render();
  }
}

async function runBotTurn() {
  if (!state.sessionId) return;
  state.requestInFlight = true;
  render();
  try {
    const payload = await api('/api/bot-turn', { session_id: state.sessionId });
    applyPayload(payload);
    render();
  } catch (err) {
    alert(err.message);
  } finally {
    state.requestInFlight = false;
    state.pendingBotTimeout = null;
    blurControls();
    render();
  }
}

function scheduleBotTurnIfNeeded() {
  clearBotDelay();
  const payload = state.payload;
  if (!payload || payload.done || !payload.pending_bot_turn) return;
  state.pendingBotTimeout = setTimeout(() => {
    runBotTurn();
  }, BOT_THINK_MS);
}

async function playAction(actionIndex) {
  if (!state.sessionId || state.requestInFlight) return;
  clearBotDelay();
  blurControls();
  state.requestInFlight = true;
  render();
  try {
    const payload = await api('/api/action', { session_id: state.sessionId, action_index: actionIndex });
    state.selectedCardKeys = [];
    applyPayload(payload);
    render();
    scheduleBotTurnIfNeeded();
  } catch (err) {
    alert(err.message);
  } finally {
    state.requestInFlight = false;
    render();
  }
}

els.newGameBtn.addEventListener('click', () => startNewGame().catch((err) => alert(err.message)));
els.startingPlayer.addEventListener('change', () => startNewGame().catch((err) => alert(err.message)));

els.playBtn.addEventListener('click', () => {
  const action = selectedAction();
  if (!action) {
    alert('Pick cards that exactly match one of the legal moves.');
    return;
  }
  playAction(action.index);
});

els.passBtn.addEventListener('click', () => {
  const passAction = (state.payload?.legal_actions || []).find((action) => action.is_pass);
  if (!passAction) {
    alert('Pass is not legal right now.');
    return;
  }
  playAction(passAction.index);
});

els.clearBtn.addEventListener('click', () => {
  blurControls();
  state.selectedCardKeys = [];
  render();
});

(function initDrawPile() {
  renderStaticDrawPile();
})();

(async function init() {
  try {
    await loadHealth();
    await startNewGame();
  } catch (_) {
    // health text already updated
  }
})();
