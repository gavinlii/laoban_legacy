const API_BASE = (window.LAOBAN_API_BASE || '').replace(/\/$/, '');

const RANK_LABELS = {11: 'J', 12: 'Q', 13: 'K', 14: 'A', 17: '2', 20: 'SJ', 30: 'BJ'};
const SUIT_SYMBOLS = {H: '♥', D: '♦', C: '♣', S: '♠'};

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

function currentScores(payload) {
  const scores = payload.scores || payload.score || {};
  return {
    you: scores.you ?? 0,
    bot: scores.bot ?? 0,
    pot: scores.pot ?? payload.pot ?? 0,
  };
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

function cardFaceHtml(rawCard) {
  const card = cardDisplay(rawCard);
  if (card.rank === 20 || card.rank === 30) {
    return `<div class="joker-art ${card.rank === 20 ? 'small' : 'big'}">
      <div class="frame-top">JOKER</div>
      <div class="emblem">${card.rank === 20 ? '✦' : '✹'}</div>
      <div class="frame-bottom">${card.rank === 20 ? 'SMALL' : 'BIG'}</div>
    </div>`;
  }

  if ([11, 12, 13].includes(card.rank)) {
    const emblem = card.rank === 11 ? '♞' : card.rank === 12 ? '♛' : '♚';
    return `<div class="face-art ${card.colorClass}">
      <div class="frame-top">${card.suitText}</div>
      <div class="emblem">${emblem}</div>
      <div class="frame-bottom">${card.suitText}</div>
    </div>`;
  }

  const pipCount = Math.min(Math.max(card.rank, 1), 10);
  const pips = Array.from({ length: pipCount }, () => `<span>${card.suitText || '•'}</span>`).join('');
  return `<div class="pip-grid ${pipCount >= 8 ? 'tight' : ''}">${pips}</div>`;
}

function createCardElement(rawCard, options = {}) {
  const faceDown = !!options.faceDown;
  const clickable = !!options.clickable;
  const playable = !!options.playable;
  const selected = !!options.selected;
  const card = cardDisplay(rawCard || { rank: 0, suit: null, key: '' });

  const el = document.createElement('div');
  el.className = [
    'card',
    faceDown ? 'back' : card.colorClass,
    clickable ? 'clickable' : '',
    playable ? 'playable' : '',
    selected ? 'selected' : '',
  ].filter(Boolean).join(' ');

  if (faceDown) {
    el.innerHTML = `<div class="back-center"></div>`;
  } else {
    const topIcon = card.suitText || '★';
    el.innerHTML = `
      <div class="card-shadow"></div>
      <div class="corner top">
        <div class="rank">${card.rankLabel}</div>
        <div class="suit">${topIcon}</div>
      </div>
      <div class="center">${cardFaceHtml(card)}</div>
      <div class="corner bottom">
        <div class="rank">${card.rankLabel}</div>
        <div class="suit">${topIcon}</div>
      </div>
    `;
  }

  if (clickable && typeof options.onClick === 'function') {
    el.addEventListener('click', options.onClick);
  }

  return el;
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

function render() {
  const payload = state.payload;
  if (!payload) return;

  const scores = currentScores(payload);
  const playable = new Set(payload.playable_card_keys || []);

  els.status.textContent = payload.status || `You ${scores.you}   ·   Bot ${scores.bot}   ·   Pot ${scores.pot}`;
  const turnOwner = payload.turn === 'you' ? 'You' : payload.turn === 'bot' ? 'Bot' : 'Game Over';
  els.turn.textContent = `Turn: ${turnOwner}   ·   Hand type: ${payload.hand_type || 'open'}`;
  els.wins.textContent = `Wins - You: ${payload.wins?.you ?? 0}   ·   Bot: ${payload.wins?.bot ?? 0}`;
  els.deckSize.textContent = `${payload.deck_size ?? 0} card${(payload.deck_size ?? 0) === 1 ? '' : 's'}`;
  els.opponentStatus.textContent = `Cards in hand: ${payload.opponent_card_count ?? 0}`;
  els.lastMove.textContent = `Last move: ${payload.last_move ? payload.last_move.label : 'None'}`;
  els.result.textContent = payload.result || '';
  els.selection.textContent = selectedMoveText();
  els.log.textContent = (payload.log || []).join('\n');

  els.humanHand.innerHTML = '';
  (payload.human_hand || []).forEach((card) => {
    const el = createCardElement(card, {
      clickable: payload.turn === 'you' && !payload.done,
      playable: playable.has(card.key),
      selected: state.selectedCardKeys.includes(card.key),
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
    els.humanHand.appendChild(el);
  });

  els.opponentHand.innerHTML = '';
  for (let i = 0; i < (payload.opponent_card_count || 0); i += 1) {
    els.opponentHand.appendChild(createCardElement(null, { faceDown: true }));
  }

  els.tableCards.innerHTML = '';
  els.tableCards.classList.toggle('empty-state', !(payload.last_move && !payload.last_move.is_pass));
  if (payload.last_move && !payload.last_move.is_pass) {
    (payload.last_move.cards || []).forEach((card) => {
      els.tableCards.appendChild(createCardElement(card));
    });
  } else {
    els.tableCards.textContent = 'No active table move';
  }

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
  if (!response.ok) {
    throw new Error(data.detail || 'Request failed');
  }
  return data;
}

async function loadHealth() {
  const response = await fetch(endpoint('/health'));
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || 'Health check failed');
  }
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
