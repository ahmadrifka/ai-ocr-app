const DASHBOARD_URL = "/dashboard/";

const form = document.getElementById("login-form");
const passwordInput = document.getElementById("login-password");
const submitButton = document.getElementById("login-submit");
const errorMessage = document.getElementById("login-error");

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.hidden = true;
  if (!passwordInput.value) {
    showError("Enter the password.");
    return;
  }

  submitButton.disabled = true;
  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: passwordInput.value }),
    });
    if (response.ok) {
      window.location.assign(DASHBOARD_URL);
      return;
    }
    showError(response.status === 401 ? "Incorrect password." : `Sign in failed (${response.status}).`);
  } catch {
    showError("Could not reach the server. Try again.");
  } finally {
    submitButton.disabled = false;
  }
});
