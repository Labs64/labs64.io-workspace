// Shared across every page: a plain `<form>` submission blocks on a full navigation with no
// browser chrome of its own, so any button that triggers one (refresh, running a declared
// action) needs its own immediate feedback that the click was received and is in flight.
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.classList.contains("btn-form")) return;
  const button = form.querySelector("button[type=submit]");
  if (!button) return;
  button.disabled = true;
  button.classList.add("is-loading");
  button.textContent = "Working…";
});
