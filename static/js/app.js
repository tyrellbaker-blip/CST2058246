document.getElementById("task-form").addEventListener("submit", function(e) {
    e.preventDefault();
    const input = document.getElementById("task-input");
    const message = input.value.trim();

    if (message) {
        addMessage("user", message);
        input.value = "";
        showTypingIndicator();

        fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: message })
        })
        .then(res => res.json())
        .then(data => {
            hideTypingIndicator();

            if (data.response === "success") {
                playSuccessAudio();
                addMessage("bot", data.message || "✅ Scheduled!");
            } else if (data.response === "conflict" || data.response === "error") {
                playFailureAudio();
                addMessage("bot", data.message || "❌ Something went wrong.");
            } else if (data.response === "followup") {
                addMessage("bot", data.message || "🤖 Can you tell me more?");
            } else {
                addMessage("bot", "⚠️ Unexpected response. Want to try again?");
            }
            input.focus();
        })
        .catch(err => {
            hideTypingIndicator();
            playFailureAudio();
            addMessage("bot", "🚫 Network issue or server error. Please try again later.");
            console.error(err);
        });
    }
});

function addMessage(sender, text) {
    const chatBox = document.getElementById("chat-box");
    const messageWrapper = document.createElement("div");
    const bubble = document.createElement("div");

    if (sender === "user") {
        messageWrapper.className = "d-flex justify-content-end mb-2";
        bubble.className = "bg-primary text-white p-2 rounded-pill";
    } else {
        messageWrapper.className = "d-flex justify-content-start mb-2";
        bubble.className = "bg-light text-dark p-2 rounded-pill";
    }

    bubble.innerText = text;
    messageWrapper.appendChild(bubble);
    chatBox.appendChild(messageWrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function playSuccessAudio() {
    const audio = new Audio("/static/success.wav");
    audio.play().catch(err => console.error("Audio error:", err));
}

function playFailureAudio() {
    const audio = new Audio("/static/failure.wav");
    audio.play().catch(err => console.error("Audio error:", err));
}

// --- Typing indicator ---
let typingInterval = null;

function showTypingIndicator() {
    const chatBox = document.getElementById("chat-box");

    const wrapper = document.createElement("div");
    wrapper.className = "d-flex justify-content-start mb-2";

    const bubble = document.createElement("div");
    bubble.className = "bg-light text-dark p-2 rounded-pill";
    bubble.id = "typing-indicator";
    bubble.innerText = "Bot is typing";

    wrapper.appendChild(bubble);
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;

    let dots = "";
    typingInterval = setInterval(() => {
        dots = dots.length < 3 ? dots + "." : "";
        bubble.innerText = "Bot is typing" + dots;
    }, 500);
}

function hideTypingIndicator() {
    clearInterval(typingInterval);
    const indicator = document.getElementById("typing-indicator");
    if (indicator) {
        indicator.parentElement.remove();
    }
}

// --- FullCalendar Initialization ---
document.addEventListener('DOMContentLoaded', function () {
    const calendarEl = document.getElementById('calendar');
    if (!calendarEl) return;

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        height: 600,
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },
        events: '/events',
eventClick: function(info) {
    const event = info.event;

    // Open the event link in a new tab if it exists
    if (event.url) {
        window.open(event.url, "_blank");
        info.jsEvent.preventDefault();
        return;
    }

    // Otherwise show a delete prompt
    const confirmed = confirm(`📅 ${event.title}\nFrom: ${event.start}\nTo: ${event.end}\n\nDo you want to delete this event?`);

    if (confirmed) {
        fetch('/delete-event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: event.id })
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                alert("🗑️ Event deleted.");
                event.remove();
            } else {
                alert("⚠️ Failed to delete event.");
            }
        })
        .catch(err => {
            alert("🚫 Network error.");
            console.error(err);
        });
    }
}
    });

    calendar.render();
});

// --- Dark Mode ---
let darkMode = false;
document.getElementById("dark-mode").addEventListener("click", function () {
    darkMode = !darkMode;

    const logoImg = document.getElementById("logoBG-img");
    const bannerImg = document.getElementById("banner-img");

    if (darkMode) {
        logoImg.src = "/static/LogoBG-dark.png";
        bannerImg.src = "/static/Banner-dark.png";
        document.body.style.backgroundImage = "url('/static/Cover-dark.jpeg')";
        document.body.classList.add("dark-mode");
        this.textContent = "🔆 Light Mode";
    } else {
        logoImg.src = "/static/LogoBG.png";
        bannerImg.src = "/static/Banner.png";
        document.body.style.backgroundImage = "url('/static/Cover.jpeg')";
        document.body.classList.remove("dark-mode");
        this.textContent = "🌙 Dark Mode";
    }
});
