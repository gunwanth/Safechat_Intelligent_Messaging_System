// Auto-refresh inbox every 30 seconds
function autoRefresh() {
    setTimeout(function() {
        window.location.reload();
    }, 30000); // 30s
}

// Confirmation before marking as spam
function confirmSpam(emailId) {
    return confirm("🚨 Are you sure you want to mark email " + emailId + " as spam?");
}

// Example dynamic toast notification
function showToast(message, type="info") {
    let toast = document.createElement("div");
    toast.className = "toast " + type;
    toast.innerText = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}
