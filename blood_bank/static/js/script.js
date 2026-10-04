// Show / hide sidebar on small screens
function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("open");
}

// Login form validation
function validateLogin() {
    var u = document.getElementById("username").value.trim();
    var p = document.getElementById("password").value;
    if (u === "" || p === "") {
        alert("Please enter both username and password.");
        return false;
    }
    return true;
}

// Auto-hide success/error messages after 4 seconds
setTimeout(function () {
    document.querySelectorAll(".alert").forEach(function (a) {
        a.style.display = "none";
    });
}, 4000);
