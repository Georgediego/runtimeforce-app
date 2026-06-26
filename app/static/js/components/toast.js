import { escapeHtml } from "../utils/escape.js";

let toastContainer = null;

function getToastContainer() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'rf-toast-container';
        // Используем Tailwind для контейнера: фиксируем в правом нижнем углу поверх всего
        toastContainer.className = 'fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 pointer-events-none';
        document.body.appendChild(toastContainer);
    }
    return toastContainer;
}

export function showToast(message, type = 'info', duration = 3000) {
    const container = getToastContainer();

    const toast = document.createElement('div');
    
    // Цвета в зависимости от типа (используем ваши переменные из index.html)
    let bgClass = "bg-[var(--ide-elevated)] border-[var(--ide-border-subtle)]";
    let textClass = "text-[var(--ide-text-primary)]";
    let icon = "info";
    let iconColor = "text-[var(--ide-accent)]";

    if (type === "success") {
        icon = "check-circle";
        iconColor = "text-[var(--ide-success)]";
    } else if (type === "error") {
        icon = "x-circle";
        iconColor = "text-[var(--ide-error)]";
    } else if (type === "warning") {
        icon = "alert-triangle";
        iconColor = "text-[var(--ide-warning)]";
    }

    // Собираем тост с Tailwind классами для анимации
    toast.className = `flex items-start gap-3 px-4 py-3 rounded-xl border shadow-2xl transform transition-all duration-300 translate-y-4 opacity-0 pointer-events-auto ${bgClass} min-w-[280px] max-w-sm`;
    
    toast.innerHTML = `
        <div class="mt-0.5 shrink-0">
            <i data-lucide="${icon}" class="w-4 h-4 ${iconColor}"></i>
        </div>
        <div class="flex-1 text-sm font-medium ${textClass} leading-tight whitespace-pre-wrap">${escapeHtml(message)}</div>
        <button class="shrink-0 text-[var(--ide-text-muted)] hover:text-[var(--ide-text-primary)] transition-colors toast-close" title="Закрыть">
            <i data-lucide="x" class="w-4 h-4"></i>
        </button>
    `;

    container.appendChild(toast);

    // Инициализируем иконки Lucide
    if (typeof window.lucide !== 'undefined') {
        window.lucide.createIcons({ root: toast });
    }

    // Анимация появления
    requestAnimationFrame(() => {
        toast.classList.remove("translate-y-4", "opacity-0");
    });

    // Функция закрытия с анимацией
    const removeToast = () => {
        toast.classList.add("translate-y-4", "opacity-0");
        setTimeout(() => {
            if (toast.parentNode) toast.remove();
        }, 300);
    };

    // Обработчик кнопки закрытия
    const closeBtn = toast.querySelector('.toast-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', removeToast);
    }

    // Автоматическое закрытие
    if (duration > 0) {
        setTimeout(() => {
            if (toast.parentNode) removeToast();
        }, duration);
    }
}

// Кастомный confirm диалог с поддержкой кастомного текста на кнопках
export function showConfirm(title, message, confirmText = 'Удалить', cancelText = 'Отмена') {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        // Используем Tailwind для оверлея
        overlay.className = 'fixed inset-0 z-[10000] flex items-center justify-center bg-[rgba(0,0,0,0.7)] backdrop-blur-sm transition-opacity duration-200 opacity-0';

        overlay.innerHTML = `
            <div class="bg-[var(--ide-surface)] border border-[var(--ide-border-subtle)] rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4 transform scale-95 transition-transform duration-200 confirm-modal">
                <div class="text-lg font-bold text-[var(--ide-text-primary)] mb-2">${escapeHtml(title)}</div>
                <div class="text-sm text-[var(--ide-text-secondary)] mb-6 whitespace-pre-wrap">${escapeHtml(message)}</div>
                <div class="flex items-center justify-end gap-3">
                    <button class="px-4 py-2 rounded-lg text-sm font-medium text-[var(--ide-text-secondary)] hover:bg-[var(--ide-elevated)] hover:text-[var(--ide-text-primary)] transition-colors confirm-btn-cancel">${escapeHtml(cancelText)}</button>
                    <button class="px-4 py-2 rounded-lg text-sm font-bold bg-[var(--ide-accent)] text-white hover:brightness-110 transition-colors confirm-btn-confirm">${escapeHtml(confirmText)}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        // Анимация появления
        requestAnimationFrame(() => {
            overlay.classList.remove('opacity-0');
            overlay.querySelector('.confirm-modal').classList.remove('scale-95');
        });

        const cancelBtn = overlay.querySelector('.confirm-btn-cancel');
        const confirmBtn = overlay.querySelector('.confirm-btn-confirm');

        const close = (result) => {
            overlay.classList.add('opacity-0');
            overlay.querySelector('.confirm-modal').classList.add('scale-95');
            setTimeout(() => {
                if (overlay.parentNode) overlay.remove();
                resolve(result);
            }, 200);
        };

        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => close(false));
        }
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => close(true));
        }

        // Закрытие по клику на overlay
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                close(false);
            }
        });

        // Закрытие по Escape, подтверждение по Enter
        const handleKey = (e) => {
            if (e.key === 'Escape') {
                document.removeEventListener('keydown', handleKey);
                close(false);
            } else if (e.key === 'Enter') {
                document.removeEventListener('keydown', handleKey);
                close(true);
            }
        };
        document.addEventListener('keydown', handleKey);

        // Фокус на кнопке подтверждения
        if (confirmBtn) {
            setTimeout(() => confirmBtn.focus(), 50);
        }
    });
}