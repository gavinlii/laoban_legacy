const API_BASE = (window.LAOBAN_API_BASE || '').replace(/\/$/, '');
const BOT_THINK_MS = 440;

const RANK_LABELS = {11: 'J', 12: 'Q', 13: 'K', 14: 'A', 17: '2', 20: 'SJ', 30: 'BJ'};
const SUIT_SYMBOLS = {H: '♥', D: '♦', C: '♣', S: '♠'};
const SUIT_COLORS = {H: '#c74343', D: '#c74343', C: '#1c1c1c', S: '#1c1c1c'};
const BACK_SUITS = ['♠', '♥', '♣', '♦'];
const NUMBER_LAYOUTS = {
  3: [[50, 51, 0], [50, 73, 0], [50, 95, 180]],
  4: [[40, 52, 0], [60, 52, 0], [40, 86, 180], [60, 86, 180]],
  5: [[40, 52, 0], [60, 52, 0], [50, 69, 0], [40, 86, 180], [60, 86, 180]],
  6: [[40, 48, 0], [60, 48, 0], [40, 72, 0], [60, 72, 0], [40, 96, 180], [60, 96, 180]],
  7: [[40, 47, 0], [60, 47, 0], [50, 62, 0], [40, 72, 0], [60, 72, 0], [40, 97, 180], [60, 97, 180]],
  8: [[40, 45, 0], [60, 45, 0], [40, 61, 0], [60, 61, 0], [40, 80, 180], [60, 80, 180], [40, 96, 180], [60, 96, 180]],
  9: [[40, 44, 0], [60, 44, 0], [40, 59, 0], [60, 59, 0], [50, 73, 0], [40, 83, 180], [60, 83, 180], [40, 98, 180], [60, 98, 180]],
  10: [[40, 43, 0], [60, 43, 0], [40, 57, 0], [60, 57, 0], [40, 72, 0], [60, 72, 0], [40, 86, 180], [60, 86, 180], [40, 100, 180], [60, 100, 180]],
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

function suitText(suit) {
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

function displayCard(rawCard) {
  return {
    ...rawCard,
    rankLabel: rawCard.rank_label || rankText(rawCard.rank),
    suitText: rawCard.suit_symbol || suitText(rawCard.suit),
    suitFill: SUIT_COLORS[rawCard.suit] || '#1c1c1c',
    colorClass: suitColor(rawCard),
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

function svgText({ x, y, text, fill, size, weight = 700, anchor = 'middle', rotate = null, family = 'Trebuchet MS, Segoe UI, sans-serif', baseline = 'middle', letterSpacing = null }) {
  const attrs = [
    `x="${x}"`,
    `y="${y}"`,
    `fill="${fill}"`,
    `font-size="${size}"`,
    `font-weight="${weight}"`,
    `font-family="${family}"`,
    `text-anchor="${anchor}"`,
    `dominant-baseline="${baseline}"`,
  ];
  if (rotate !== null) attrs.push(`transform="rotate(${rotate} ${x} ${y})"`);
  if (letterSpacing !== null) attrs.push(`letter-spacing="${letterSpacing}"`);
  return `<text ${attrs.join(' ')}>${text}</text>`;
}

function polygonPoints(inset = 0) {
  const i = inset;
  return `${12 + i},${i} ${88 - i},${i} ${100 - i},${12 + i} ${100 - i},${128 - i} ${88 - i},${140 - i} ${12 + i},${140 - i} ${i},${128 - i} ${i},${12 + i}`;
}

function frontBaseSvg(card) {
  const topIcon = card.suitText || '★';
  const topColor = card.suitText ? card.suitFill : '#b88928';
  return `
    <polygon points="${polygonPoints(0)}" fill="#fff9ec" stroke="#45614f" stroke-width="0"/>
    <polygon points="${polygonPoints(2)}" fill="#fff9ec" stroke="#d9d2c2" stroke-width="1.6"/>
    <line x1="24" y1="14" x2="76" y2="14" stroke="#cfc7b5" stroke-width="1.6" stroke-linecap="round"/>
    <line x1="24" y1="126" x2="76" y2="126" stroke="#cfc7b5" stroke-width="1.6" stroke-linecap="round"/>
    <line x1="14" y1="24" x2="14" y2="116" stroke="#d4cdbc" stroke-width="1.4" stroke-linecap="round"/>
    <line x1="86" y1="24" x2="86" y2="116" stroke="#d4cdbc" stroke-width="1.4" stroke-linecap="round"/>
    ${svgText({ x: 26, y: 26, text: card.rankLabel, fill: card.suitFill, size: 12, weight: 800, anchor: 'middle', baseline: 'middle' })}
    ${svgText({ x: 26, y: 41, text: topIcon, fill: topColor, size: 12, weight: 700, anchor: 'middle', baseline: 'middle', family: 'Georgia, Times New Roman, serif' })}
    ${svgText({ x: 74, y: 114, text: card.rankLabel, fill: card.suitFill, size: 12, weight: 800, anchor: 'middle', baseline: 'middle', rotate: 180 })}
    ${svgText({ x: 74, y: 99, text: topIcon, fill: topColor, size: 12, weight: 700, anchor: 'middle', baseline: 'middle', rotate: 180, family: 'Georgia, Times New Roman, serif' })}
  `;
}

function pipSvg(card, x, y, size, rotate = 0) {
  return svgText({
    x,
    y,
    text: card.suitText,
    fill: card.suitFill,
    size,
    weight: 700,
    rotate,
    family: 'Georgia, Times New Roman, serif',
    baseline: 'middle',
  });
}

function pipFieldSvg(card) {
  const rank = card.rank;
  if (rank === 14) {
    return pipSvg(card, 50, 78, 26, 0);
  }
  if (rank === 17) {
    return `${pipSvg(card, 50, 47, 16, 0)}${pipSvg(card, 50, 101, 16, 180)}`;
  }
  const layout = NUMBER_LAYOUTS[rank] || [[50, 55, 0]];
  return layout.map(([x, y, rotate = 0]) => pipSvg(card, x, y, 15, rotate)).join('');
}

function faceFieldSvg(card) {
  const emblem = card.rank === 11 ? '♞' : card.rank === 12 ? '♛' : '♚';
  const jewel = card.rank === 11 ? '◆' : card.rank === 12 ? '●' : '♢';
  const wingFill = card.suitFill === '#1c1c1c' ? '#d7d0c1' : '#e3d2d2';
  return `
    <polygon points="28,34 72,34 78,40 78,100 72,106 28,106 22,100 22,40" fill="#fbf4e7" stroke="#d7cebb" stroke-width="1.6"/>
    <line x1="30" y1="49" x2="70" y2="49" stroke="#d8cdb9" stroke-width="1.6"/>
    <line x1="30" y1="91" x2="70" y2="91" stroke="#d8cdb9" stroke-width="1.6"/>
    <polygon points="22,70 30,52 30,88" fill="${wingFill}"/>
    <polygon points="78,70 70,52 70,88" fill="${wingFill}"/>
    ${svgText({ x: 50, y: 44, text: card.suitText, fill: card.suitFill, size: 15, weight: 700, family: 'Georgia, Times New Roman, serif' })}
    ${svgText({ x: 50, y: 65, text: emblem, fill: '#b88928', size: 22, weight: 700, family: 'Georgia, Times New Roman, serif' })}
    ${svgText({ x: 50, y: 86, text: jewel, fill: card.suitFill, size: 16, weight: 700, family: 'Georgia, Times New Roman, serif' })}
    ${svgText({ x: 50, y: 98, text: card.suitText, fill: card.suitFill, size: 15, weight: 700, family: 'Georgia, Times New Roman, serif', rotate: 180 })}
  `;
}

function jokerFieldSvg(card) {
  const small = card.rank === 20;
  const accent = small ? '#6e59d9' : '#303030';
  const halo = small ? '#e9e1ff' : '#ece6db';
  const emblem = small ? '✦' : '✹';
  const jewel = small ? '◆' : '●';
  return `
    <polygon points="28,34 72,34 78,40 78,100 72,106 28,106 22,100 22,40" fill="#fbf4e7" stroke="#d7cebb" stroke-width="1.6"/>
    <line x1="30" y1="49" x2="70" y2="49" stroke="#d8cdb9" stroke-width="1.6"/>
    <line x1="30" y1="91" x2="70" y2="91" stroke="#d8cdb9" stroke-width="1.6"/>
    ${svgText({ x: 50, y: 43, text: 'JOKER', fill: accent, size: 8.7, weight: 800, letterSpacing: '0.9px' })}
    <circle cx="50" cy="71" r="15" fill="${halo}" stroke="#d7cebb" stroke-width="1.1"/>
    ${svgText({ x: 50, y: 67, text: emblem, fill: accent, size: 20, weight: 700, family: 'Georgia, Times New Roman, serif' })}
    ${svgText({ x: 50, y: 82, text: jewel, fill: accent, size: 12, weight: 700, family: 'Georgia, Times New Roman, serif' })}
    ${svgText({ x: 50, y: 97, text: small ? 'SMALL' : 'BIG', fill: accent, size: 8.6, weight: 800, letterSpacing: '0.8px', rotate: 180 })}
  `;
}

function frontCardSvg(rawCard) {
  const card = displayCard(rawCard);
  let center = '';
  if (card.rank === 20 || card.rank === 30) center = jokerFieldSvg(card);
  else if ([11, 12, 13].includes(card.rank)) center = faceFieldSvg(card);
  else center = pipFieldSvg(card);

  return `
    <svg class="card-svg" viewBox="0 0 100 140" aria-hidden="true">
      ${frontBaseSvg(card)}
      ${center}
    </svg>
  `;
}

function backCardSvg() {
  return `
    <svg class="card-svg" viewBox="0 0 100 140" aria-hidden="true">
      <polygon points="${polygonPoints(0)}" fill="#21395e" stroke="#9bb8ea" stroke-width="2.4" stroke-linejoin="round"/>
      <polygon points="${polygonPoints(4)}" fill="#2c4673" stroke="#8fb7ff" stroke-width="1.6" stroke-linejoin="round"/>
      <rect x="29" y="28" width="9" height="58" rx="2.5" fill="#6f8fc2" fill-opacity=".28"/>
      <rect x="45.5" y="28" width="9" height="58" rx="2.5" fill="#6f8fc2" fill-opacity=".28"/>
      <rect x="62" y="28" width="9" height="58" rx="2.5" fill="#6f8fc2" fill-opacity=".28"/>
      ${svgText({ x: 50, y: 58, text: BACK_SUITS.join(' '), fill: '#f5efe1', size: 18.8, weight: 700, family: 'Georgia, Times New Roman, serif', letterSpacing: '0.2px' })}
      ${svgText({ x: 50, y: 100, text: '5 · 10 · K', fill: '#f5efe1', size: 10.8, weight: 700 })}
      <line x1="30" y1="114" x2="70" y2="114" stroke="#8fb7ff" stroke-width="1.7" stroke-linecap="round" opacity=".9"/>
    </svg>
  `;
}

function createFaceDownCard() {
  const el = document.createElement('div');
  el.className = 'card-shell back';
  el.innerHTML = `
    <div class="card-shadow"></div>
    <div class="card-body">
      <div class="card-glow"></div>
      <div class="card-plate">${backCardSvg()}</div>
    </div>
  `;
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

  wrapper.innerHTML = `
    <div class="card-shadow"></div>
    <div class="card-body">
      <div class="card-glow"></div>
      <div class="card-plate">${frontCardSvg(card)}</div>
    </div>
  `;

  if (clickable && options.onClick) wrapper.addEventListener('click', options.onClick);
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
    move.textContent = payload.done ? 'Game over' : (payload.pending_bot_turn ? '' : 'Waiting for bot…');
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
  els.selection.textContent = payload.pending_bot_turn ? '' : selectedMoveText();
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
    for (const card of payload.last_move.cards) row.appendChild(createCardElement(card));
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
    scheduleBotTurnIfNeeded();
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
  state.pendingBotTimeout = setTimeout(() => runBotTurn(), BOT_THINK_MS);
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
