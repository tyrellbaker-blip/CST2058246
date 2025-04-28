document.getElementById("task-form").addEventListener("submit", function(e) {
    e.preventDefault();
    const input = document.getElementById("task-input");
    const message = input.value.trim();

    if (message)
    {
        addMessage("user", message);
        input.value = "";
        showTypingIndicator();

        fetch("/chat",{
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({message: message})
        })
            .then(res=> res.json())
            .then(data=> {
                hideTypingIndicator();
                addMessage("bot", data.response);
            })
            .catch(err=> {
                hideTypingIndicator();
                addMessage("bot", "Sorry about that, something went wrong. Give it another go.");
                console.error(err);
            })
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