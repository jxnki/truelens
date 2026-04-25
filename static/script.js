function triggerUpload() {
    document.getElementById("imageInput").click();
}

function getResultState(top) {
    const normalized = (top.label || "").toLowerCase();
    const rawScore = Number(top.score) || 0;
    const confidence = rawScore > 1 ? rawScore / 100 : rawScore;
    const isDeepfakeClass = normalized.includes("deepfake") || normalized.includes("fake") || normalized.includes("ai");
    const realConfidence = isDeepfakeClass ? 1 - confidence : confidence;

    if (realConfidence >= 0.75) {
        return {
            tone: "real",
            badge: "🟢 Real Image",
            description:
                "This image appears consistent with real-world photography, with natural textures and no strong signs of AI manipulation.",
        };
    }

    if (realConfidence >= 0.5) {
        return {
            tone: "real",
            badge: "🟢 Possibly Real",
            description:
                "This image appears mostly consistent with a real photograph, but a few details may still need verification.",
        };
    }

    if (realConfidence >= 0.35) {
        return {
            tone: "uncertain",
            badge: "🟡 Uncertain",
            description:
                "This image has mixed signals. It may be real or AI-generated, so treat it carefully and verify the source.",
        };
    }

    if (realConfidence >= 0.2) {
        return {
            tone: "ai",
            badge: "🔴 Possibly AI-generated",
            description:
                "This image shows some signs that can appear in AI-generated content, so it should be reviewed carefully.",
        };
    }

    return {
        tone: "ai",
        badge: "🔴 AI-generated",
        description:
            "This image shows patterns commonly found in AI-generated content, such as unnatural textures or inconsistencies in facial details.",
    };
}

function resetResult() {
    const resultPanel = document.getElementById("resultPanel");
    const result = document.getElementById("result");
    const explanation = document.getElementById("explanation");
    const nextSteps = document.getElementById("nextSteps");
    const imagePreview = document.getElementById("imagePreview");
    const previewFrame = document.getElementById("previewFrame");

    resultPanel.hidden = true;
    resultPanel.classList.remove("is-ai", "is-real");
    result.textContent = "";
    result.classList.remove("is-ai", "is-real", "is-error");
    explanation.textContent = "";
    nextSteps.hidden = true;
    previewFrame.hidden = true;
    imagePreview.removeAttribute("src");
}

function uploadImage() {
    const fileInput = document.getElementById("imageInput");
    const file = fileInput.files[0];
    const resultPanel = document.getElementById("resultPanel");
    const result = document.getElementById("result");
    const explanation = document.getElementById("explanation");
    const nextSteps = document.getElementById("nextSteps");
    const previewFrame = document.getElementById("previewFrame");
    const imagePreview = document.getElementById("imagePreview");

    if (!file) {
        alert("Please upload an image");
        return;
    }

    document.getElementById("fileName").innerText = file.name;
    resultPanel.hidden = false;
    resultPanel.classList.remove("is-ai", "is-real");
    result.classList.remove("is-ai", "is-real", "is-error");
    nextSteps.hidden = true;
    previewFrame.hidden = false;
    imagePreview.src = URL.createObjectURL(file);
    result.innerText = "Checking image...";
    explanation.innerText = "";

    const formData = new FormData();
    formData.append("image", file);

    fetch("/analyze", {
        method: "POST",
        body: formData,
    })
        .then((res) => res.json())
        .then((data) => {
            console.log(data);

            if (Array.isArray(data) && data.length > 0) {
                const top = [...data].sort((a, b) => (b.score || 0) - (a.score || 0))[0];
                const resultState = getResultState(top);
                const normalizedScore = (Number(top.score) || 0) > 1 ? Number(top.score) / 100 : Number(top.score);
                const realConfidence = resultState.tone === "real" ? normalizedScore : 1 - normalizedScore;
                const score = (realConfidence * 100).toFixed(2);

                resultPanel.classList.add(`is-${resultState.tone}`);
                result.classList.add(`is-${resultState.tone}`);
                result.innerText = `${resultState.badge} (${score}%)`;
                explanation.innerText = resultState.description;
                nextSteps.hidden = resultState.tone !== "ai";
            } else if (data && data.error) {
                result.innerText = `Error: ${data.error}${data.detail ? ` - ${data.detail}` : ""}`;
                result.classList.add("is-error");
                explanation.innerText = "";
                nextSteps.hidden = true;
            } else {
                result.innerText = "Unexpected response from server";
                result.classList.add("is-error");
                explanation.innerText = "";
                nextSteps.hidden = true;
            }
        })
        .catch((err) => {
            console.log(err);
            result.innerText = "Network error while analyzing image";
            result.classList.add("is-error");
            explanation.innerText = "";
            nextSteps.hidden = true;
        });
}

document.addEventListener("DOMContentLoaded", function () {
    const uploadButton = document.getElementById("uploadButton");
    const checkButton = document.getElementById("checkButton");
    const fileInput = document.getElementById("imageInput");

    resetResult();

    uploadButton.addEventListener("click", triggerUpload);
    checkButton.addEventListener("click", uploadImage);

    fileInput.addEventListener("change", function () {
        const file = this.files[0];
        document.getElementById("fileName").innerText = file ? file.name : "No image selected";
        resetResult();

        if (file) {
            const previewFrame = document.getElementById("previewFrame");
            const imagePreview = document.getElementById("imagePreview");
            previewFrame.hidden = false;
            imagePreview.src = URL.createObjectURL(file);
        }
    });
});
