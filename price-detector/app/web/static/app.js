// Minimal, dependency-free helpers: fragment polling + handoff POST.

// Poll a results fragment until the run reaches a terminal state.
function pollResults(runId) {
  const target = document.getElementById("results");
  if (!target) return;
  let stop = false;
  async function tick() {
    if (stop) return;
    try {
      const res = await fetch(`/runs/${runId}/results`);
      target.innerHTML = await res.text();
      const marker = target.querySelector("[data-run-status]");
      const state = marker ? marker.getAttribute("data-run-status") : null;
      if (state === "done" || state === "failed") {
        stop = true;
        return;
      }
    } catch (e) {
      /* keep polling */
    }
    setTimeout(tick, 2000);
  }
  tick();
}

// Buy-at-this-price handoff: POST and show a toast inline.
async function handoff(form) {
  const data = new FormData(form);
  const toast = form.querySelector(".toast-slot") || document.getElementById("toast-slot");
  try {
    const res = await fetch("/handoff", { method: "POST", body: data });
    if (toast) toast.innerHTML = await res.text();
  } catch (e) {
    if (toast) toast.innerHTML = '<p class="toast error">Handoff failed.</p>';
  }
  return false;
}
