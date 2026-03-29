const API_BASE = (window.LAOBAN_API_BASE || '').replace(/\/$/, '');

const RANK_LABELS = {11: 'J', 12: 'Q', 13: 'K', 14: 'A', 17: '2', 20: 'SJ', 30: 'BJ'};
const SUIT_SYMBOLS = {H: '♥', D: '♦', C: '♣', S: '♠'};
const PIP_COUNTS = {3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 14: 1, 17: 2};
const PIP_LAYOUTS = {
  1: [[50, 50, 0]],
  2: [[50, 30, 0], [50, 70, 180]],
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
  selectedActionIndex: null,
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
  return card.suit === 'H' || card.suit === 'D' ? 'red' : 'black';
}

function cardDisplay(card) {
  return {
    ...card,
    rankLabel: card.rank_label || rankText(card.rank),
    suitText: card.suit_symbol || suitSymbol(card.suit),
    colorClass: card.color || suitColor(card),
  };
}

function currentScores(payload) {
  const scores = payload.scores || payload.score || {};
  return {
    you: scores.you ?? 0,
    bot: scores.bot ?? 0,
    pot: scores.pot ?? payload.pot ?? 0,
  };
}

function sameKeys(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function actionCardKeys(action) {
  return (action.cards || []).map((c) => c.key).sort();
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

function pipMarkup(card) {
  const count = PIP_COUNTS[card.rank] || 1;
  const layout = PIP_LAYOUTS[count] || PIP_LAYOUTS[1];
  const pip = card.suitText || '•';
  return `
    <div class="pip-field ${count >= 8 ? 'tight' : ''}">
      ${layout.map(([x, y, angle]) => `
        <span class="pip" style="left:${x}%; top:${y}%; transform: translate(-50%, -50%) rotate(${angle}deg);">${pip}</span>
      `).join('')}
    </div>
  `;
}

function faceMarkup(card) {
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
      <div class="frame-suit top">${card.suitText}</div>
      <div class="frame-emblem">${emblem}</div>
      <div class="frame-jewel">${jewel}</div>
      <div class="frame-suit bottom">${card.suitText}</div>
    </div>
  `;
}

function jokerMarkup(card) {
  return `
    <div class="art-frame joker-frame ${card.rank === 20 ? 'small' : 'big'}">
      <div class="frame-rule top"></div>
      <div class="frame-rule bottom"></div>
      <div class="frame-word top">JOKER</div>
      <div class="frame-emblem">${card.rank === 20 ? '✦' : '✹'}</div>
      <div class="frame-jewel ${card.rank === 20 ? 'diamond' : 'orb'}"></div>
      <div class="frame-word bottom">${card.rank === 20 ? 'SMALL' : 'BIG'}</div>
    </div>
  `;
}

function cardCenterMarkup(rawCard) {
  const card = cardDisplay(rawCard);
  if (card.rank === 20 || card.rank === 30) return jokerMarkup(card);
  if ([11, 12, 13].includes(card.rank)) return faceMarkup(card);
  return pipMarkup(card);
}

function createFaceDownCard() {
  const el = document.createElement('div');
  el.className = 'card-shell back';
  el.innerHTML = `
    <div class="card-shadow"></div>
    <div class="card-back-outer">
      <div class="card-back-inner">
        <div class="back-bars"></div>
        <div class="back-badge top">♠ ♥ ♣ ♦</div>
        <div class="back-badge bottom">5 · 10 · K</div>
      </div>
    </div>
  `;
  return el;
}

function createCardElement(rawCard, options = {}) {
  const clickable = !!options.clickable;
  const playable = !!options.playable;
  const selected = !!options.selected;
  const card = cardDisplay(rawCard);

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
        <div class="corner top ${card.suitText ? '' : 'star'}">
          <div class="rank">${card.rankLabel}</div>
          <div class="suit">${topIcon}</div>
        </div>
        <div class="corner bottom ${card.suitText ? '' : 'star'}">
          <div class="rank">${card.rankLabel}</div>
          <div class="suit">${topIcon}</div>
        </div>
        <div class="card-center">${cardCenterMarkup(card)}</div>
      </div>
    </div>
  `;

  if (clickable && typeof options.onClick === 'function') {
    wrapper.addEventListener('click', options.onClick);
  }
  return wrapper;
}

function renderMoveBrowser(payload) {
  els.moves.innerHTML = '';
  const legalActions = payload.legal_actions || [];
  if (!legalActions.length) {
    const row = document.createElement('div');
    row.className = 'move disabled';
    row.textContent = payload.done ? 'Game over' : 'Waiting for bot...';
    els.moves.appendChild(row);
    return;
  }

  legalActions.forEach((action) => {
    const row = document.createElement('div');
    row.className = [
      'move',
      action.is_pass ? 'pass' : '',
      state.selectedActionIndex === action.index ? 'selected' : '',
    ].filter(Boolean).join(' ');
    row.textContent = action.label;
    row.addEventListener('click', () => {
      state.selectedActionIndex = action.index;
      state.selectedCardKeys = (action.cards || []).map((card) => card.key);
      render();
    });
    row.addEventListener('dblclick', () => playAction(action.index).catch((err) => alert(err.message)));
    els.moves.appendChild(row);
  });
}

function renderCardRow(container, cards, { clickable = false, playable = new Set(), selected = [] } = {}) {
  container.innerHTML = '';
  cards.forEach((card) => {
    const el = createCardElement(card, {
      clickable,
      playable: playable.has(card.key),
      selected: selected.includes(card.key),
      onClick: () => {
        if (state.selectedCardKeys.includes(card.key)) {
          state.selectedCardKeys = state.selectedCardKeys.filter((key) => key !== card.key);
        } else {
          state.selectedCardKeys = [...state.selectedCardKeys, card.key];
        }
        state.selectedActionIndex = null;
        render();
      },
    });
    container.appendChild(el);
  });
}

function renderOpponentRow(count) {
  els.opponentHand.innerHTML = '';
  for (let i = 0; i < count; i += 1) {
    els.opponentHand.appendChild(createFaceDownCard());
  }
}

function renderTable(payload) {
  els.tableCards.innerHTML = '';
  const move = payload.last_move;
  els.tableCards.classList.toggle('empty-state', !(move && !move.is_pass));
  if (move && !move.is_pass) {
    const title = document.createElement('div');
    title.className = 'table-move-type';
    title.textContent = move.type.toUpperCase();
    els.tableCards.appendChild(title);

    const row = document.createElement('div');
    row.className = 'table-card-strip';
    (move.cards || []).forEach((card) => row.appendChild(createCardElement(card)));
    els.tableCards.appendChild(row);
  } else {
    els.tableCards.textContent = 'No active table move';
  }
}

function render() {
  const payload = state.payload;
  if (!payload) return;

  const scores = currentScores(payload);
  const playable = new Set(payload.playable_card_keys || []);
  const humanCards = payload.human_hand || [];
  const opponentCount = payload.opponent_card_count || 0;

  els.status.textContent = payload.status || `You ${scores.you}   ·   Bot ${scores.bot}   ·   Pot ${scores.pot}`;
  const turnOwner = payload.turn === 'you' ? 'You' : payload.turn === 'bot' ? 'Bot' : 'Game Over';
  els.turn.textContent = `Turn: ${turnOwner}   ·   Hand type: ${payload.hand_type || 'open'}`;
  els.wins.textContent = `Wins - You: ${payload.wins?.you ?? 0}   ·   Bot: ${payload.wins?.bot ?? 0}`;
  els.deckSize.textContent = `${payload.deck_size ?? 0} card${(payload.deck_size ?? 0) === 1 ? '' : 's'}`;
  els.opponentStatus.textContent = `Cards in hand: ${opponentCount}`;
  els.lastMove.textContent = `Last move: ${payload.last_move ? payload.last_move.label : 'None'}`;
  els.result.textContent = payload.result || '';
  els.selection.textContent = selectedMoveText();
  els.log.textContent = (payload.log || []).join('\n');

  renderOpponentRow(opponentCount);
  renderCardRow(els.humanHand, humanCards, {
    clickable: payload.turn === 'you' && !payload.done,
    playable,
    selected: state.selectedCardKeys,
  });
  renderTable(payload);
  renderMoveBrowser(payload);

  const canPass = payload.turn === 'you' && (payload.legal_actions || []).some((action) => action.is_pass);
  const canPlaySelected = payload.turn === 'you' && !!selectedAction();
  els.passBtn.disabled = !canPass;
  els.playBtn.disabled = !canPlaySelected;
  els.clearBtn.disabled = state.selectedCardKeys.length === 0;
}

async function api(path, body, method = 'POST') {
  const response = await fetch(endpoint(path), {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: method === 'GET' ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

async function loadHealth() {
  const response = await fetch(endpoint('/health'));
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Health check failed');
  els.meta.textContent = `Connected to ${API_BASE || 'same-origin API'}  |  encoder: ${data.encoder}  |  dims: ${data.state_dim}/${data.action_dim}  |  checkpoint: ${data.checkpoint}`;
}

async function startNewGame() {
  const payload = await api('/api/new-game', { bot_first: els.startingPlayer.value === 'bot' });
  state.sessionId = payload.session_id || payload.game_id;
  state.payload = payload;
  state.selectedCardKeys = [];
  state.selectedActionIndex = null;
  render();
}

async function playAction(actionIndex) {
  if (!state.sessionId) return;
  const payload = await api('/api/action', { session_id: state.sessionId, action_index: actionIndex });
  state.payload = payload;
  state.selectedCardKeys = [];
  state.selectedActionIndex = null;
  render();
}

els.newGameBtn.addEventListener('click', () => {
  startNewGame().catch((err) => alert(err.message));
});

els.startingPlayer.addEventListener('change', () => {
  startNewGame().catch((err) => alert(err.message));
});

els.playBtn.addEventListener('click', () => {
  const action = selectedAction();
  if (!action) {
    alert('Pick cards that exactly match one of the legal moves.');
    return;
  }
  playAction(action.index).catch((err) => alert(err.message));
});

els.passBtn.addEventListener('click', () => {
  const passAction = (state.payload?.legal_actions || []).find((action) => action.is_pass);
  if (!passAction) {
    alert('Pass is not legal right now.');
    return;
  }
  playAction(passAction.index).catch((err) => alert(err.message));
});

els.clearBtn.addEventListener('click', () => {
  state.selectedCardKeys = [];
  state.selectedActionIndex = null;
  render();
});

(async function init() {
  try {
    await loadHealth();
    await startNewGame();
  } catch (err) {
    els.meta.innerHTML = `<span class="error">Backend connection failed.</span> ${err.message}`;
  }
})();
