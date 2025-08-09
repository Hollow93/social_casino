// social_casino_frontend/app.js

/*
A fast simplex noise implementation in Javascript.
Copyright 2022-2023 C. Amstra
Licensed under the MIT license.
*/
function createNoise2D(random = Math.random) {
    const e = new Uint8Array(512);
    let t;
    t = random;
    for (let r = 0; r < 256; r++) e[r] = r;
    let r;
    for (let o = 0; o < 255; o++) {
        r = o + ~~(t() * (256 - o));
        const s = e[o];
        (e[o] = e[r]), (e[r] = s);
    }
    for (let o = 0; o < 256; o++) e[o + 256] = e[o];
    const o = 0.5 * (Math.sqrt(3) - 1),
        s = (3 - Math.sqrt(3)) / 6;
    return function (t, r) {
        const f = (t + r) * o,
            a = Math.floor(t + f),
            n = Math.floor(r + f),
            i = (a + n) * s,
            l = t - a + i,
            c = r - n + i;
        let h, d;
        l > c ? ((h = 1), (d = 0)) : ((h = 0), (d = 1));
        const u = l - h + s,
            p = c - d + s,
            m = l - 1 + 2 * s,
            g = c - 1 + 2 * s,
            y = e[a & 255],
            w = e[(y + h) & 255],
            q = e[(y + 1) & 255],
            x = 0.5 - l * l - c * c;
        let v;
        v =
            x < 0
                ? 0
                : x *
                x *
                x *
                x *
                (function (t, r) {
                    const o = e[t & 255];
                    return e[(o + r) & 255];
                })(a, n);
        const M = 0.5 - u * u - p * p;
        let b;
        b =
            M < 0
                ? 0
                : M *
                M *
                M *
                M *
                (function (t, r) {
                    const o = e[t & 255];
                    return e[(o + r) & 255];
                })(a + h, n + d);
        const N = 0.5 - m * m - g * g;
        let I;
        return (
            (I =
                N < 0
                    ? 0
                    : N *
                    N *
                    N *
                    N *
                    (function (t, r) {
                        const o = e[t & 255];
                        return e[(o + r) & 255];
                    })(a + 1, n + 1)),
            70 * (v + b + I)
        );
    };
}

document.addEventListener("DOMContentLoaded", () => {
    const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

    // Telegram WebApp boot
    try {
        tg?.ready();
        tg?.expand();
    } catch (e) {
        console.warn("Not in Telegram env.");
    }

    // ======= CONFIG =======
    // WebSocket API домен (проксируется Caddy на backend:8000)
    const WEBSOCKET_URL = "wss://api.skill-forge-factory.ru";
    const WS_PATH = "/ws";

    // HTTP API (инвойсы Stars)
    const API_BASE = "https://api.skill-forge-factory.ru";

    // ======= DOM refs =======
    const multiplierDisplayEl = document.getElementById("multiplier-display");
    const statusTextEl = document.getElementById("status-text");
    const historyBarEl = document.getElementById("history-bar");
    const balanceEl = document.getElementById("balance");
    const betPanels = [
        document.getElementById("bet-panel-0"),
        document.getElementById("bet-panel-1"),
    ];
    const graphCanvas = document.getElementById("crashChart");
    const graphCtx = graphCanvas.getContext("2d");
    const particlesCanvas = document.getElementById("particles-canvas");
    const particlesCtx = particlesCanvas.getContext("2d");

    // ======= THEME =======
    const styles = getComputedStyle(document.documentElement);
    const C_BLUE = styles.getPropertyValue("--blue-accent").trim();
    const C_BLUE_GLOW = styles.getPropertyValue("--blue-glow").trim();
    const C_PURPLE = styles.getPropertyValue("--purple-accent").trim();
    const C_PURPLE_GLOW = styles.getPropertyValue("--purple-glow").trim();
    const C_RED = styles.getPropertyValue("--red-accent").trim();
    const C_RED_GLOW = styles.getPropertyValue("--red-glow").trim();
    const C_TEXT = styles.getPropertyValue("--text-color").trim();

    // ======= STATE =======
    let ws;
    let balance = 0.0;
    let gameState = "connecting";
    let roundStartTime = 0;
    let animationTimestamp = 0;
    let isRoundActive = false;

    const panelStates = [
        {
            status: "idle",
            amount: 10.0,
            winAmount: 0,
            autoBet: false,
            autoCashoutToggle: false,
            autoCashoutValue: 2.0,
        },
        {
            status: "idle",
            amount: 10.0,
            winAmount: 0,
            autoBet: false,
            autoCashoutToggle: false,
            autoCashoutValue: 2.0,
        },
    ];

    let graphState = {
        color: C_BLUE,
        glow: C_BLUE_GLOW,
        points: [],
        viewPort: { x: 5, y: 2 },
        targetViewPort: { x: 5, y: 2 },
    };

    const getMultiplierFromDuration = (d) => Math.pow(Math.E, 0.06 * d);
    const getDurationFromMultiplier = (m) => Math.log(m) / 0.06;

    // ======= PARTICLES =======
    let particles = [];
    function setupParticles() {
        const dpr = window.devicePixelRatio || 1;
        const rect = particlesCanvas.getBoundingClientRect();
        if (rect.width === 0) return;
        particlesCanvas.width = rect.width * dpr;
        particlesCanvas.height = rect.height * dpr;
        particlesCtx.setTransform(1, 0, 0, 1, 0, 0);
        particlesCtx.scale(dpr, dpr);
        particles = [];
        let numParticles = Math.floor(rect.width / 15);
        for (let i = 0; i < numParticles; i++) {
            particles.push({
                x: Math.random() * rect.width,
                y: Math.random() * rect.height,
                vx: (Math.random() - 0.5) * 0.4,
                vy: Math.random() * 0.3 + 0.1,
                radius: Math.random() * 2 + 1,
                alpha: Math.random() * 0.7 + 0.2,
            });
        }
    }

    function animateParticles() {
        const w = particlesCanvas.width / (window.devicePixelRatio || 1);
        const h = particlesCanvas.height / (window.devicePixelRatio || 1);
        particlesCtx.clearRect(0, 0, w, h);
        particles.forEach((p) => {
            p.x += p.vx + Math.sin(p.y / 20) * 0.1;
            p.y += p.vy;
            if (p.y > h + p.radius) {
                p.y = -p.radius;
                p.x = Math.random() * w;
            }
            if (p.x > w + p.radius) p.x = -p.radius;
            if (p.x < -p.radius) p.x = w + p.radius;
            particlesCtx.beginPath();
            particlesCtx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            particlesCtx.fillStyle = `rgba(220, 220, 240, ${p.alpha})`;
            particlesCtx.fill();
        });
    }

    // ======= GRAPH =======
    function drawWarpingGrid(timestamp) {
        const dpr = window.devicePixelRatio || 1;
        const width = graphCanvas.width / dpr;
        const height = graphCanvas.height / dpr;

        graphCtx.save();
        graphCtx.strokeStyle = "rgba(48, 54, 61, 0.3)";
        graphCtx.lineWidth = 1;

        const gridSize = 40;
        const time = timestamp * 0.0000001;
        const noiseScale = 0.05;
        const noiseAmount = 2.5;
        const noise2D = createNoise2D();

        const getDisplacedPoint = (x, y) => {
            const noiseVal = noise2D(x * noiseScale + time, y * noiseScale);
            const angle = noiseVal * Math.PI * 2;
            return {
                x: x + Math.cos(angle) * noiseAmount,
                y: y + Math.sin(angle) * noiseAmount,
            };
        };

        const startX = -gridSize;
        const startY = -gridSize;
        const endX = width + gridSize;
        const endY = height + gridSize;

        for (let x = startX; x < endX; x += gridSize) {
            graphCtx.beginPath();
            let firstPoint = getDisplacedPoint(x, startY);
            graphCtx.moveTo(firstPoint.x, firstPoint.y);
            for (let y = startY + gridSize; y < endY; y += gridSize) {
                const p = getDisplacedPoint(x, y);
                graphCtx.lineTo(p.x, p.y);
            }
            graphCtx.stroke();
        }

        for (let y = startY; y < endY; y += gridSize) {
            graphCtx.beginPath();
            let firstPoint = getDisplacedPoint(startX, y);
            graphCtx.moveTo(firstPoint.x, firstPoint.y);
            for (let x = startX + gridSize; x < endX; x += gridSize) {
                const p = getDisplacedPoint(x, y);
                graphCtx.lineTo(p.x, p.y);
            }
            graphCtx.stroke();
        }
        graphCtx.restore();
    }

    function drawGraph() {
        const dpr = window.devicePixelRatio || 1;
        const width = graphCanvas.width / dpr;
        const height = graphCanvas.height / dpr;

        if (graphState.points.length < 2) return;

        graphState.viewPort.x += (graphState.targetViewPort.x - graphState.viewPort.x) * 0.08;
        graphState.viewPort.y += (graphState.targetViewPort.y - graphState.viewPort.y) * 0.08;

        const toScreenX = (t) => (t / graphState.viewPort.x) * width;
        const toScreenY = (m) => height - ((m - 1) / (graphState.viewPort.y - 1)) * height;

        const lastPoint = graphState.points[graphState.points.length - 1];
        graphCtx.save();
        graphCtx.strokeStyle = graphState.color;
        graphCtx.lineWidth = Math.min(6, 3 + lastPoint.multiplier / 20);
        graphCtx.shadowColor = graphState.glow;
        graphCtx.shadowBlur = 20;

        graphCtx.beginPath();
        graphCtx.moveTo(toScreenX(graphState.points[0].time), toScreenY(graphState.points[0].multiplier));

        for (let i = 1; i < graphState.points.length; i++) {
            graphCtx.lineTo(toScreenX(graphState.points[i].time), toScreenY(graphState.points[i].multiplier));
        }
        graphCtx.stroke();
        graphCtx.restore();
    }

    function masterAnimationLoop(timestamp) {
        animationTimestamp = timestamp;
        const dpr = window.devicePixelRatio || 1;
        const rect = graphCanvas.getBoundingClientRect();
        if (graphCanvas.width !== rect.width * dpr || graphCanvas.height !== rect.height * dpr) {
            graphCanvas.width = rect.width * dpr;
            graphCanvas.height = rect.height * dpr;
            graphCtx.setTransform(1, 0, 0, 1, 0, 0);
            graphCtx.scale(dpr, dpr);
        }
        graphCtx.clearRect(0, 0, rect.width, rect.height);

        drawWarpingGrid(timestamp);

        if (isRoundActive) {
            const elapsed = (Date.now() - roundStartTime) / 1000;
            const multiplier = getMultiplierFromDuration(elapsed);

            const lastPoint = graphState.points[graphState.points.length - 1];
            if (!lastPoint || elapsed > lastPoint.time + 0.016) {
                graphState.points.push({ time: elapsed, multiplier });
            }

            graphState.targetViewPort.x = Math.max(5, elapsed * 1.3);
            graphState.targetViewPort.y = Math.max(2, multiplier * 1.3);

            multiplierDisplayEl.textContent = `${multiplier.toFixed(2)}x`;

            if (multiplier >= 10) {
                graphState.color = C_RED;
                graphState.glow = C_RED_GLOW;
                multiplierDisplayEl.style.color = C_RED;
            } else if (multiplier >= 2) {
                graphState.color = C_PURPLE;
                graphState.glow = C_PURPLE_GLOW;
                multiplierDisplayEl.style.color = C_PURPLE;
            } else {
                graphState.color = C_BLUE;
                graphState.glow = C_BLUE_GLOW;
                multiplierDisplayEl.style.color = C_TEXT;
            }

            panelStates.forEach((state, id) => {
                if (state.status === "active") {
                    betPanels[id].querySelector(".button-value").textContent = `💎 ${(state.amount * multiplier).toFixed(2)}`;
                    if (state.autoCashoutToggle && multiplier >= state.autoCashoutValue) cashOut(id);
                }
            });
        }

        if (graphState.points.length > 0) {
            drawGraph();
        }

        animateParticles();
        requestAnimationFrame(masterAnimationLoop);
    }

    // ======= UI updates =======
    const updateBalance = (newBalance) => {
        balance = newBalance;
        balanceEl.textContent = `💎 ${balance.toFixed(2)}`;
    };

    const updatePanelUI = (panelId) => {
        const state = panelStates[panelId];
        const panel = betPanels[panelId];
        const actionBtn = panel.querySelector(".action-button");
        const btnText = panel.querySelector(".button-text");
        const btnValue = panel.querySelector(".button-value");
        const amountInput = panel.querySelector(".bet-amount-input");
        const modifierBtns = panel.querySelectorAll(".bet-modifier-btn");
        panel.classList.remove("active", "won");
        amountInput.disabled = state.status !== "idle";
        modifierBtns.forEach((btn) => (btn.disabled = state.status !== "idle"));
        btnValue.textContent = "";

        switch (state.status) {
            case "idle":
                btnText.textContent = "Place Bet";
                actionBtn.className = "action-button state-bet";
                actionBtn.disabled = gameState !== "waiting";
                break;
            case "pending":
                btnText.textContent = "Pending...";
                actionBtn.className = "action-button state-pending";
                actionBtn.disabled = true;
                break;
            case "active":
                btnText.textContent = "Cash Out";
                actionBtn.className = "action-button state-cashout";
                actionBtn.disabled = gameState !== "running";
                panel.classList.add("active");
                break;
            case "cashed_out":
                btnText.textContent = "Cashed Out";
                actionBtn.className = "action-button state-cashed-out";
                btnValue.textContent = `💎 ${state.winAmount.toFixed(2)}`;
                actionBtn.disabled = true;
                panel.classList.add("won");
                break;
        }
    };

    const updateAllPanelsUI = () => panelStates.forEach((_, id) => updatePanelUI(id));

    // ======= WS =======
    function connectWebSocket() {
        // Требуется Telegram для auth
        if (!tg || !tg.initData) {
            console.error("Telegram initData is missing. Cannot connect.");
            statusTextEl.textContent = "Auth Error";
            statusTextEl.className = "status-text-overlay";
            return;
        }

        ws = new WebSocket(WEBSOCKET_URL + WS_PATH);

        ws.onopen = () => {
            console.log("WebSocket connected!");
            // Handshake c initData
            ws.send(
                JSON.stringify({
                    action: "handshake",
                    init_data: tg.initData,
                })
            );
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleWebSocketMessage(msg);
            } catch (e) {
                console.error("WS parse error:", e);
            }
        };

        ws.onclose = (event) => {
            gameState = "connecting";
            isRoundActive = false;
            if (event.code === 1008) {
                statusTextEl.textContent = "Auth Failed!";
            } else {
                statusTextEl.textContent = "Reconnecting...";
                setTimeout(connectWebSocket, 3000);
            }
            statusTextEl.className = "status-text-overlay";
            multiplierDisplayEl.classList.remove("visible");
            updateAllPanelsUI();
        };
    }

    function sendToServer(payload) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(payload));
        }
    }

    function handleWebSocketMessage({ type, data }) {
        switch (type) {
            case "balance_update":
                updateBalance(data.balance);
                break;

            case "waiting":
                gameState = "waiting";
                isRoundActive = false;
                graphState.points = [];
                graphState.targetViewPort = { x: 5, y: 2 };
                statusTextEl.className = "status-text-overlay waiting";
                statusTextEl.textContent = `Starts in ${data.countdown}s`;
                multiplierDisplayEl.classList.remove("visible");
                updateHistory(data.history);

                if (!data.is_initial_sync) {
                    panelStates.forEach((state, id) => {
                        if (state.status !== "pending") {
                            state.status = "idle";
                            state.winAmount = 0;
                        }
                        if (state.autoBet && state.status !== "pending") {
                            placeBet(id);
                        }
                    });
                }
                updateAllPanelsUI();
                break;

            case "round_start":
                gameState = "running";
                isRoundActive = true;
                roundStartTime = data.startTime * 1000;
                statusTextEl.className = "status-text-overlay running";
                multiplierDisplayEl.classList.add("visible");
                if (data.is_initial_sync) updateHistory(data.history);

                graphState.points = [{ time: 0, multiplier: 1 }];

                panelStates.forEach((state) => {
                    if (state.status === "pending") state.status = "active";
                });
                updateAllPanelsUI();
                break;

            case "round_end":
                gameState = "crashed";
                isRoundActive = false;
                graphState.color = C_RED;
                graphState.glow = C_RED_GLOW;
                statusTextEl.className = "status-text-overlay crashed";
                statusTextEl.textContent = `Crashed @ ${data.crashPoint.toFixed(2)}x`;
                multiplierDisplayEl.classList.remove("visible");
                updateHistory(data.history);

                const duration = getDurationFromMultiplier(data.crashPoint);
                graphState.points = [];
                for (let t = 0; t <= duration; t += 0.02) {
                    const m = getMultiplierFromDuration(t);
                    if (m > data.crashPoint) break;
                    graphState.points.push({ time: t, multiplier: m });
                }
                graphState.points.push({ time: duration, multiplier: data.crashPoint });

                graphState.targetViewPort.x = Math.max(5, duration * 1.3);
                graphState.targetViewPort.y = Math.max(2, data.crashPoint * 1.3);

                panelStates.forEach((state, id) => {
                    if (state.status === "active") state.status = "idle";
                    updatePanelUI(id);
                });
                break;

            case "bet_confirm":
                // можно подсветить панель
                break;

            case "bet_result":
                const state = panelStates[data.panelId];
                if (data.winAmount > 0) {
                    state.status = "cashed_out";
                    state.winAmount = data.winAmount;
                } else {
                    state.status = "idle";
                }
                updatePanelUI(data.panelId);
                break;

            case "bet_error":
                tg?.showAlert?.(`Bet Error: ${data.message}`);
                panelStates[data.panelId].status = "idle";
                updatePanelUI(data.panelId);
                break;
        }
    }

    function updateHistory(history) {
        historyBarEl.innerHTML = history
            .map(({ multiplier }) => {
                let cn = "low";
                if (multiplier >= 100) cn = "epic";
                else if (multiplier >= 10) cn = "high";
                else if (multiplier >= 2) cn = "medium";
                return `<div class="history-item ${cn}">${multiplier.toFixed(2)}x</div>`;
            })
            .join("");
    }

    // ======= Actions =======
    function placeBet(panelId) {
        const state = panelStates[panelId];
        const panel = betPanels[panelId];
        const amount = parseFloat(panel.querySelector(".bet-amount-input").value);
        if (isNaN(amount) || amount <= 0) return;

        if (balance < amount && !state.autoBet) {
            tg?.showConfirm?.(
                "Not enough crystals. Top up your balance?",
                async (confirmed) => {
                    if (confirmed) {
                        try {
                            const response = await fetch(`${API_BASE}/create-star-invoice`, {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json",
                                    "ngrok-skip-browser-warning": "true",
                                },
                                body: JSON.stringify({
                                    user_id: tg?.initDataUnsafe?.user?.id,
                                    amount: 100,
                                }),
                            });
                            const data = await response.json();

                            if (data.ok && data.invoice_link) {
                                tg.openInvoice(data.invoice_link, (status) => {
                                    if (status === "paid") {
                                        tg.showAlert("Payment successful! Your balance will be updated shortly.");
                                    } else if (status === "failed") {
                                        tg.showAlert("Payment failed.");
                                    }
                                });
                            } else {
                                tg.showAlert("Could not create payment request. Please try again later.");
                            }
                        } catch (error) {
                            console.error("Payment error:", error);
                            tg?.showAlert?.("An error occurred during payment.");
                        }
                    }
                }
            );
            return;
        }

        if ((gameState === "waiting" || state.autoBet) && state.status === "idle") {
            state.amount = amount;
            state.status = "pending";
            state.autoCashoutValue = parseFloat(
                panel.querySelector(`#auto-cashout-input-${panelId}`).value
            );
            sendToServer({
                type: "place_bet",
                panelId,
                amount,
                autoCashoutAt: state.autoCashoutToggle ? state.autoCashoutValue : null,
            });
            updatePanelUI(panelId);
        }
    }

    function cashOut(panelId) {
        const state = panelStates[panelId];
        if (gameState === "running" && state.status === "active") {
            state.status = "pending_cashout";
            sendToServer({ type: "cash_out", panelId });
        }
    }

    // ======= Bindings =======
    betPanels.forEach((panel, id) => {
        panel.querySelector(".action-button").addEventListener("click", () => {
            if (panelStates[id].status === "idle") placeBet(id);
            else if (panelStates[id].status === "active") cashOut(id);
        });
        panel.querySelector(`#auto-bet-toggle-${id}`).addEventListener("change", (e) => {
            panelStates[id].autoBet = e.target.checked;
            if (e.target.checked && gameState === "waiting" && panelStates[id].status === "idle") {
                placeBet(id);
            }
        });
        panel.querySelector(`#auto-cashout-toggle-${id}`).addEventListener("change", (e) => {
            panelStates[id].autoCashoutToggle = e.target.checked;
        });
        panel.querySelectorAll(".bet-modifier-btn").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                const input = panel.querySelector(".bet-amount-input");
                let val = parseFloat(input.value);
                val *= e.currentTarget.dataset.action === "double" ? 2 : 0.5;
                input.value = Math.max(0, val).toFixed(2);
            });
        });
    });

    window.addEventListener("resize", () => {
        setupParticles();
    });

    // ======= Start =======
    updateAllPanelsUI();
    connectWebSocket();
    setupParticles();
    requestAnimationFrame(masterAnimationLoop);

    // ======= DEBUG helper (внутри Telegram DevTools) =======
    window.__tgDump = function () {
        const webapp = window.Telegram?.WebApp;
        if (!webapp) {
            console.log("Telegram.WebApp недоступен. Открой WebApp внутри Telegram.");
            alert("Открой WebApp внутри Telegram.");
            return;
        }
        console.log("initData:", webapp.initData);
        try {
            navigator.clipboard.writeText(webapp.initData).then(
                () => alert("initData скопирован в буфер"),
                () => alert("Скопируй initData из консоли.")
            );
        } catch (e) {
            alert("Скопируй initData из консоли.");
        }
    };
});
