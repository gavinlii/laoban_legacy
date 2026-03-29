const API_BASE = (window.LAOBAN_API_BASE || '').replace(/\/$/, '');

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
  const map = {11: 'J', 12: 'Q', 13: 'K', 14: 'A', 17: '2', 20: 'SJ', 30: 'BJ'};
  return map[rank] || String(rank);
}

function suitSymbol(suit) {
  return {H: '♥', D: '♦', C: '♣', S: '♠', null: ''}[suit] || '';
}

function faceMarkup(card) {
  if (card.rank === 20 || card.rank === 30) {
    return `<div class="joker">JOKER<br><span class="mini">${card.rank === 20 ? 'SMALL' : 'BIG'}</span></div>`;
  }
  if ([11, 12, 13].includes(card.rank)) {
    return `<div class="face">${rankText(card.rank)}<br><span class="mini">FACE</span></div>`;
  }
  return `<div class="pip-grid">${Array.from({ length: Math.min(card.rank, 10) }).map(() => `<div>${suitSymbol(card.suit)}</div>`).join('')}</div>`;
}

function createCardElement(card, options = {}) {
  const faceDown = !!options.faceDown;
  const clickable = !!options.clickable;
  const playable = !!options.playable;
  const selected = !!options.selected;

  const el = document.createElement('div');
  el.className = [
    'card',
    faceDown ? 'back' : (card.color || 'black'),
    clickable ? 'clickable' : '',
    playable ? 'playable' : '',
    selected ? 'selected' : '',
  ].filter(Boolean).join(' ');

  if (!faceDown) {
    el.innerHTML = `
      <div class="corner top">
        <div class="rank">${card.rank_label}</div>
        <div class="suit">${card.suit_symbol || ''}</div>
      </div>
      <div class="center">${faceMarkup(card)}</div>
      <div class="corner bottom">
        <div class="rank">${card.rank_label}</div>
        <div class="suit">${card.suit_symbol || ''}</div>
      </div>
    `;
  }

  if (clickable && options.onClick) {
    el.addEventListener('click', options.onClick);
  }
  return el;
}

function cardKeysForAction(action) {
  return (action.cards || []).map(card => card.key).sort();
}

function sameKeys(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function legalActionForCurrentSelection() {
  if (!state.payload) return null;
  const selected = [...state.selectedCardKeys].sort();
  return state.payload.legal_actions.find(action => !action.is_pass && sameKeys(cardKeysForAction(action), selected)) || null;
}

function selectedMoveText() {
  const action = legalActionForCurrentSelection();
  if (action) return action.label;
  if (!state.selectedCardKeys.length) return 'No cards selected.';
  return 'Selected cards do not form a legal move.';
}

function render() {
  const payload = state.payload;
  if (!payload) return;

  const playable = new Set();
  for (const action of payload.legal_actions || []) {
    if (!action.is_pass) {
      for (const card of action.cards) playable.add(card.key);
    }
  }

  els.status.textContent = `You ${payload.score.you} · Bot ${payload.score.bot} · Pot ${payload.pot}`;
  els.turn.textContent = `Turn: ${payload.turn} · Hand type: ${payload.hand_type}`;
  els.wins.textContent = `Wins - You: ${payload.wins.you} · Bot: ${payload.wins.bot}`;
  els.deckSize.textContent = `${payload.deck_size} card${payload.deck_size === 1 ? '' : 's'}`;
  els.opponentStatus.textContent = `Cards in hand: ${payload.opponent_card_count}`;
  els.lastMove.textContent = `Last move: ${payload.last_move ? payload.last_move.label : 'None'}`;
  els.result.textContent = payload.result || '';
  els.selection.textContent = selectedMoveText();
  els.log.textContent = (payload.log || []).join('\n');

  els.humanHand.innerHTML = '';
  for (const card of payload.human_hand) {
    const selected = state.selectedCardKeys.includes(card.key);
    const el = createCardElement(card, {
      clickable: payload.turn === 'you' && !payload.done,
      playable: playable.has(card.key),
      selected,
      onClick: () => toggleCard(card.key),
    });
    els.humanHand.appendChild(el);
  }

  els.opponentHand.innerHTML = '';
  for (let i = 0; i < payload.opponent_card_count; i += 1) {
    els.opponentHand.appendChild(createCardElement({ color: 'black' }, { faceDown: true }));
  }

  els.tableCards.innerHTML = '';
  els.tableCards.classList.remove('empty-state');
  if (payload.last_move && !payload.last_move.is_pass) {
    for (const card of payload.last_move.cards) {
      els.tableCards.appendChild(createCardElement(card));
    }
  } else {
    els.tableCards.textContent = 'No active table move';
    els.tableCards.classList.add('empty-state');
  }

  els.moves.innerHTML = '';
  for (const action of payload.legal_actions || []) {
    const move = document.createElement('div');
    move.className = `move${action.is_pass ? ' pass' : ''}${state.selectedActionIndex === action.index ? ' selected' : ''}`;
    move.textContent = action.label;
    move.addEventListener('click', () => selectAction(action));
    move.addEventListener('dblclick', () => playAction(action.index));
    els.moves.appendChild(move);
  }
  if (!(payload.legal_actions || []).length) {
    const move = document.createElement('div');
    move.className = 'move';
    move.textContent = payload.done ? 'Game over' : 'Waiting for bot...';
    els.moves.appendChild(move);
  }

  const canPlaySelected = payload.turn === 'you' && !!legalActionForCurrentSelection();
  const canPass = payload.turn === 'you' && (payload.legal_actions || []).some(a => a.is_pass);
  const canClear = state.selectedCardKeys.length > 0;
  els.playBtn.disabled = !canPlaySelected;
  els.passBtn.disabled = !canPass;
  els.clearBtn.disabled = !canClear;
}

function toggleCard(key) {
  if (!state.payload || state.payload.turn !== 'you' || state.payload.done) return;
  if (state.selectedCardKeys.includes(key)) {
    state.selectedCardKeys = state.selectedCardKeys.filter(k => k !== key);
  } else {
    state.selectedCardKeys = [...state.selectedCardKeys, key];
  }
  state.selectedActionIndex = null;
  render();
}

function selectAction(action) {
  state.selectedActionIndex = action.index;
  state.selectedCardKeys = action.cards.map(card => card.key);
  render();
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

async function loadHealth() {
  try {
    const res = await fetch(endpoint('/health'));
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Health check failed');
    els.meta.textContent = `Connected to ${API_BASE || 'same-origin API'} | encoder: ${data.encoder} | dims: ${data.state_dim}/${data.action_dim} | checkpoint: ${data.checkpoint}`;
  } catch (err) {
    els.meta.innerHTML = `<span class="error">Backend connection failed.</span> Set <code>window.LAOBAN_API_BASE</code> in <code>config.js</code> to your deployed Python API, such as <code>https://api.laoban.cards</code>.`;
    throw err;
  }
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

els.newGameBtn.addEventListener('click', () => startNewGame().catch(err => alert(err.message)));
els.playBtn.addEventListener('click', () => {
  const action = legalActionForCurrentSelection();
  if (!action) {
    alert('Pick cards that exactly match one of the legal moves.');
    return;
  }
  playAction(action.index).catch(err => alert(err.message));
});
els.passBtn.addEventListener('click', () => {
  const passAction = state.payload?.legal_actions.find(action => action.is_pass);
  if (!passAction) {
    alert('Pass is not legal right now.');
    return;
  }
  playAction(passAction.index).catch(err => alert(err.message));
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
  } catch (_) {
    // meta already updated
  }
})();