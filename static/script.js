const dconf = document.getElementById('dconf');
const tconf = document.getElementById('tconf');
const dval = document.getElementById('dval');
const tval = document.getElementById('tval');
const landmarks = document.getElementById('landmarks');
const fps = document.getElementById('fps');
const snapBtn = document.getElementById('snapBtn');
const videoImg = document.getElementById('video');
const gestureBox = document.getElementById('gestureBox');
const framesCountEl = document.getElementById('framesCount');

// show initial values
dval.innerText = dconf.value;
tval.innerText = tconf.value;

function debounce(fn, delay=300){
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(()=>fn(...args), delay); }
}

async function pushSettings(){
  const payload = {
    min_detection_confidence: parseFloat(dconf.value),
    min_tracking_confidence: parseFloat(tconf.value),
    show_landmarks: landmarks.checked,
    show_fps: fps.checked
  };
  try {
    await fetch('/update_settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
  } catch (err) {
    console.error('Settings update failed', err);
  }
}

const debPush = debounce(pushSettings, 400);

dconf.addEventListener('input', () => { dval.innerText = dconf.value; debPush(); });
tconf.addEventListener('input', () => { tval.innerText = tconf.value; debPush(); });
landmarks.addEventListener('change', debPush);
fps.addEventListener('change', debPush);

// Snapshot: capture current displayed image and POST to server
snapBtn.addEventListener('click', async () => {
  const img = videoImg;
  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth || img.width;
  canvas.height = img.naturalHeight || img.height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/png');

  try {
    const res = await fetch('/snapshot', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({image: dataUrl})
    });
    const j = await res.json();
    if (j.status === 'saved') {
      alert('Snapshot saved: ' + j.filename);
    } else {
      alert('Snapshot failed');
    }
  } catch (err) {
    console.error(err);
    alert('Snapshot error');
  }
});

// Optional: poll status every second to update label & frames count
async function pollStatus(){
  try {
    const res = await fetch('/status');
    const j = await res.json();
    if (j.last_gesture) {
      document.getElementById('gestureBox').innerText = j.last_gesture;
    }
    if (j.frames_processed !== undefined) {
      framesCountEl.innerText = j.frames_processed;
    }
  } catch (err) {
    // ignore
  } finally {
    setTimeout(pollStatus, 1000);
  }
}
pollStatus();
