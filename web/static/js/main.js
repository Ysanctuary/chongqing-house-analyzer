// 自动 active 高亮（按 URL 匹配 nav-link）
(function() {
  const curPath = window.location.pathname;
  document.querySelectorAll('.nav-link').forEach(a => {
    const href = a.getAttribute('href');
    if (href && (href === curPath || (curPath === '/index.html' && href === '/'))) {
      a.classList.add('active');
    }
  });
})();

/* ================= 粒子背景 ================= */
(function() {
    const canvas = document.getElementById('particles-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let particles = [];
    let animationId;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    function createParticle() {
        return {
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            vx: (Math.random() - 0.5) * 0.5,
            vy: (Math.random() - 0.5) * 0.5,
            radius: Math.random() * 1.5 + 0.5,
            color: `rgba(${Math.random() < 0.5 ? '102, 126, 234' : '240, 147, 251'}, ${Math.random() * 0.5 + 0.2})`
        };
    }

    function init() {
        resize();
        const count = Math.min(80, Math.floor((canvas.width * canvas.height) / 20000));
        particles = Array.from({ length: count }, createParticle);
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => {
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
            if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            ctx.fillStyle = p.color;
            ctx.fill();
        });

        // 连线
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 120) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(102, 126, 234, ${0.15 * (1 - dist / 120)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
        animationId = requestAnimationFrame(draw);
    }

    // 检查是否启用 prefers-reduced-motion
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        canvas.style.display = 'none';
        return;
    }

    init();
    draw();
    window.addEventListener('resize', () => {
        cancelAnimationFrame(animationId);
        init();
        draw();
    });
})();

/* ================= 数字滚动动画 ================= */
function animateNumber(el, target, duration = 1500) {
    const start = 0;
    const startTime = performance.now();
    const isFloat = String(target).includes('.');

    function update(now) {
        const elapsed = now - startTime;
        const t = Math.min(elapsed / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3);  // easeOutCubic
        const current = start + (target - start) * ease;
        if (isFloat) {
            el.textContent = current.toFixed(0);
        } else {
            el.textContent = Math.floor(current).toLocaleString('zh-CN');
        }
        if (t < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

/* ================= 磁性按钮 ================= */
document.addEventListener('mousemove', (e) => {
    document.querySelectorAll('.btn, .stat-card').forEach(el => {
        const rect = el.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;
        const dist = Math.sqrt(x * x + y * y);
        if (dist < 200) {
            const force = (1 - dist / 200) * 0.15;
            el.style.transform = `translate(${x * force}px, ${y * force}px) translateY(-2px)`;
        } else {
            el.style.transform = '';
        }
    });
});

/* ================= 键盘导航 ================= */
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
    const links = ['/', '/map', '/charts', '/analysis', '/conclusion'];
    const idx = links.findIndex(l => window.location.pathname === l || (window.location.pathname === '/index.html' && l === '/'));
    if (idx === -1) return;
    if (e.key === 'ArrowRight' && idx < links.length - 1) {
        window.location.href = links[idx + 1];
    } else if (e.key === 'ArrowLeft' && idx > 0) {
        window.location.href = links[idx - 1];
    }
});

/* ================= 自定义光标 ================= */
(function() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const cursor = document.createElement('div');
    cursor.style.cssText = `
        position: fixed;
        width: 20px;
        height: 20px;
        border: 2px solid rgba(102, 126, 234, 0.6);
        border-radius: 50%;
        pointer-events: none;
        z-index: 9999;
        transition: width 0.2s, height 0.2s, transform 0.1s;
        transform: translate(-50%, -50%);
        mix-blend-mode: difference;
    `;
    document.body.appendChild(cursor);

    const trail = [];
    for (let i = 0; i < 5; i++) {
        const t = document.createElement('div');
        t.style.cssText = `
            position: fixed;
            width: ${8 - i}px;
            height: ${8 - i}px;
            background: rgba(102, 126, 234, ${0.4 - i * 0.06});
            border-radius: 50%;
            pointer-events: none;
            z-index: 9998;
            transform: translate(-50%, -50%);
        `;
        document.body.appendChild(t);
        trail.push(t);
    }

    document.addEventListener('mousemove', (e) => {
        cursor.style.left = e.clientX + 'px';
        cursor.style.top = e.clientY + 'px';
        trail.forEach((t, i) => {
            setTimeout(() => {
                t.style.left = e.clientX + 'px';
                t.style.top = e.clientY + 'px';
            }, i * 30);
        });
    });

    document.addEventListener('mousedown', () => {
        cursor.style.width = '32px';
        cursor.style.height = '32px';
    });
    document.addEventListener('mouseup', () => {
        cursor.style.width = '20px';
        cursor.style.height = '20px';
    });
})();

/* ================= 通用 fetch 封装 ================= */
async function fetchJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
}

/* ================= ECharts 主题 ================= */
const ECHART_THEME = {
    backgroundColor: 'transparent',
    textStyle: { color: '#a0aec0' },
    title: {
        textStyle: { color: '#ffffff', fontWeight: 600 },
        left: 'left',
    },
    legend: {
        textStyle: { color: '#a0aec0' },
        top: 'top',
    },
    grid: { left: '3%', right: '4%', bottom: '8%', containLabel: true },
    xAxis: {
        axisLine: { lineStyle: { color: 'rgba(160, 174, 192, 0.3)' } },
        axisLabel: { color: '#a0aec0' },
        splitLine: { lineStyle: { color: 'rgba(160, 174, 192, 0.1)' } },
    },
    yAxis: {
        axisLine: { lineStyle: { color: 'rgba(160, 174, 192, 0.3)' } },
        axisLabel: { color: '#a0aec0' },
        splitLine: { lineStyle: { color: 'rgba(160, 174, 192, 0.1)' } },
    },
    tooltip: {
        backgroundColor: 'rgba(10, 10, 15, 0.9)',
        borderColor: 'rgba(102, 126, 234, 0.3)',
        textStyle: { color: '#ffffff' },
    },
    color: ['#667eea', '#f093fb', '#ffd93d', '#6ee7b7', '#a78bfa', '#fb923c'],
    animationDuration: 1200,
    animationEasing: 'cubicOut',
};

/* ================= ECharts helpers ================= */
function barGrad(c1, c2, dir) {
    if (dir === 'h') return { type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
        colorStops: [{ offset: 0, color: c1 }, { offset: 1, color: c2 }] };
    return { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: c1 }, { offset: 1, color: c2 }] };
}
function barFade(c, dir) {
    if (dir === 'h') return barGrad(c, c.replace(')', ',0.3)').replace('rgb(', 'rgba('));
    return barGrad(c, c.replace(')', ',0.15)').replace('rgb(', 'rgba('));
}
function barGlow(c) {
    return { shadowColor: c || 'rgba(102, 126, 234, 0.35)', shadowBlur: 12, shadowOffsetY: 4 };
}
function pieGlow() {
    return { shadowColor: 'rgba(102, 126, 234, 0.3)', shadowBlur: 10 };
}
var emphasisBar = { emphasis: { itemStyle: { shadowBlur: 20, shadowColor: 'rgba(102, 126, 234, 0.5)' } } };
var emphasisPie = { emphasis: { itemStyle: { shadowBlur: 24, shadowColor: 'rgba(102, 126, 234, 0.5)' }, scaleSize: 8 }, animationType: 'scale', animationEasing: 'elasticOut' };

/* ================= 页面加载动画（仿 jiejoe.com） ================= */
(function() {
    const loading = document.querySelector('.loading');
    if (!loading) return;

    const blackblock = loading.querySelector('.loading_blackblock');
    const greenblock = loading.querySelector('.loading_greenblock');
    const animation = loading.querySelector('.loading_animation');
    let isVisible = true;
    let changer = null;

    // 初始状态：面板已覆盖屏幕（首次进入直接看到加载动画）
    gsap.set(blackblock, { x: '0%' });
    gsap.set(greenblock, { x: '0%' });
    gsap.set(animation, { opacity: 1 });

    // 页面首次加载 → 面板已在位，只需锁定滚动
    function showInitial() {
        document.body.style.overflow = 'hidden';
    }

    // 页面加载完成 → 面板滑出
    function hideLoading() {
        if (!isVisible) return;
        isVisible = false;

        // 图标跟随面板滑出，无需单独动画
        // 深色面板先滑出到右侧
        gsap.to(blackblock, {
            x: '100%',
            borderRadius: '3rem',
            duration: 1,
            delay: 0.2,
            ease: 'power4.out',
        });
        // 彩色面板稍后滑出
        gsap.to(greenblock, {
            x: '100%',
            borderRadius: '3rem',
            duration: 1,
            delay: 0.4,
            ease: 'power4.out',
            onComplete: function() {
                document.body.style.overflow = '';
                loading.style.display = 'none';
            },
        });
    }

    // 页面切换过渡（点击导航链接时触发）
    function showTransition(callback) {
        if (changer) changer.kill();
        loading.style.display = 'flex';
        isVisible = true;
        document.body.style.overflow = 'hidden';

        // 重置位置
        gsap.set(blackblock, { x: '-100%', borderRadius: '0' });
        gsap.set(greenblock, { x: '-100%', borderRadius: '0' });
        gsap.set(animation, { opacity: 1 });

        changer = gsap.timeline({
            onComplete: function() {
                // 面板完全覆盖后执行回调（页面跳转）
                if (callback) callback();
            },
        });

        // 面板滑入覆盖屏幕
        changer.to(greenblock, {
            x: '0%',
            borderRadius: '0',
            duration: 1,
            ease: 'power4.out',
        });
        changer.to(blackblock, {
            x: '0%',
            borderRadius: '0',
            duration: 1,
            delay: 0.15,
            ease: 'power4.out',
        }, '<');
        // 图标跟随面板移动，无需单独动画
    }

    // 拦截导航链接点击 → 播放过渡动画后跳转
    document.querySelectorAll('.nav-link').forEach(function(link) {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            // 只拦截内部页面链接
            if (!href || href.startsWith('http') || href.startsWith('#')) return;

            e.preventDefault();
            showTransition(function() {
                window.location.href = href;
            });
        });
    });

    // 页面首次加载流程
    showInitial();

    // 等待页面资源加载完成后隐藏加载动画
    if (document.readyState === 'complete') {
        setTimeout(hideLoading, 300);
    } else {
        window.addEventListener('load', function() {
            setTimeout(hideLoading, 300);
        });
    }
})();
