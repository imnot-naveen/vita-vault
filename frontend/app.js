'use strict';
document.documentElement.classList.add('js');
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
const hero = document.querySelector('.hero');
const device = document.querySelector('.device-wrap');
const copy = document.querySelector('.hero-copy');
const secondCopy = document.querySelector('.scroll-copy');
const wave = document.querySelector('.wave-one');
const question = document.getElementById('question');
const workspace = document.getElementById('workspace');
const response = document.getElementById('response');
const previewButton = document.getElementById('preview-motion');
const clamp = value => Math.min(1, Math.max(0, value));
let queued = false;
let previewFrame = 0;
let previewing = false;
function motion() {
 queued = false;
 if (reduced.matches) { device.style.transform = ''; copy.style.transform = ''; copy.style.opacity = ''; return; }
 const p = clamp(-hero.getBoundingClientRect().top / (hero.offsetHeight - innerHeight));
 const mobile = innerWidth < 800;
 device.style.transform = `translate(${p * (mobile ? -8 : -25)}%,${p * -10}%) rotate(${-12 + p * 16}deg) scale(${1 + p * .15})`;
 device.style.opacity = String(1 - p * .47);
 copy.style.transform = `translateY(${-p * 130}px)`;
 copy.style.opacity = String(1 - clamp(p * 2.4));
 const next = clamp((p - .42) / .35);
 secondCopy.style.opacity = String(next);
 secondCopy.style.transform = `translateY(${(1 - next) * 70}px)`;
 const areaTop = document.querySelector('.livearea').getBoundingClientRect().top;
 wave.style.transform = `translateY(${Math.max(-80, Math.min(80, areaTop * .08))}px) rotate(-14deg)`;
}
window.addEventListener('scroll', () => { if (!queued) { queued = true; requestAnimationFrame(motion); } }, {passive: true});
window.addEventListener('resize', motion);
reduced.addEventListener('change', motion);
motion();
const observer = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); } }), {threshold: .12});
document.querySelectorAll('.reveal').forEach(element => observer.observe(element));
function stopPreview() { if (!previewing) return; cancelAnimationFrame(previewFrame); previewing = false; previewButton.textContent = 'Preview scroll ↓'; }
['wheel', 'touchstart', 'keydown', 'pointerdown'].forEach(name => window.addEventListener(name, event => { if (event.target !== previewButton) stopPreview(); }, {passive:true}));
previewButton.addEventListener('click', () => {
 if (previewing) { stopPreview(); return; }
 if (reduced.matches) { workspace.scrollIntoView(); return; }
 previewing = true; previewButton.textContent = 'Stop preview';
 const from = scrollY; const to = workspace.getBoundingClientRect().top + scrollY - 90; const start = performance.now();
 function frame(time) { if (!previewing) return; const p = clamp((time-start)/11000); const eased = p*p*(3-2*p); window.scrollTo({top:from+(to-from)*eased,behavior:'instant'}); if(p<1) previewFrame=requestAnimationFrame(frame); else stopPreview(); }
 previewFrame=requestAnimationFrame(frame);
});
function selectMode(mode) { document.querySelectorAll('[data-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === mode))); document.getElementById('question-label').textContent = mode === 'ask' ? 'What would you like to know?' : 'What’s happening?'; question.placeholder = mode === 'ask' ? 'Ask about your console, setup, or an unfamiliar error.' : 'Describe the issue, any error code, and what changed before it started.'; document.dispatchEvent(new Event('question-mode-change')); }
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => selectMode(button.dataset.mode)));
document.querySelectorAll('[data-tool]').forEach(button => button.addEventListener('click', () => { const common = button.dataset.tool === 'common'; if (common) document.getElementById('problems').scrollIntoView({behavior:reduced.matches?'instant':'smooth'}); else {selectMode(button.dataset.tool); workspace.scrollIntoView({behavior:reduced.matches?'instant':'smooth'});} }));
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => { selectMode('debug'); question.value = button.dataset.question; workspace.scrollIntoView({behavior:reduced.matches?'instant':'smooth'}); }));
