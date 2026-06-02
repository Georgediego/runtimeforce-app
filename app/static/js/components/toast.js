import { escapeHtml } from "../utils/escape.js";

let toastContainer = null;

function getToastContainer() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }
    return toastContainer;
}

export function showToast(message, type = 'info', duration = 3000) {
    const container = getToastContainer();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const iconMap = {
        success: 'check-circle',
        error: 'alert-circle',
        info: 'info',
        warning: 'alert-triangle'
    };

    toast.innerHTML = `
        <div class="toast-icon">
            <i data-lucide="${iconMap[type] || 'info'}" class="w-5 h-5"></i>
        </div>
        <div class="toast-content">
            <div class="toast-message">${escapeHtml(message)}</div>
        </div>
        <div class="toast-close">
            <i data-lucide="x" class="w-4 h-4"></i>
        </div>
    `;

    container.appendChild(toast);

    // Инициализируем иконки Lucide
    if (typeof lucide !== 'undefined') {
        lucide.createIcons({
            nameAttr: 'data-lucide'
        });
    }

    // Обработчик закрытия
    const closeBtn = toast.querySelector('.toast-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            toast.classList.add('fade-out');
            setTimeout(() => {
                if (toast.parentNode) toast.remove();
            }, 300);
        });
    }

    // Автоматическое закрытие
    if (duration > 0) {
        setTimeout(() => {
            if (toast.parentNode) {
                toast.classList.add('fade-out');
                setTimeout(() => {
                    if (toast.parentNode) toast.remove();
                }, 300);
            }
        }, duration);
    }
}

// Кастомный confirm диалог с поддержкой кастомного текста на кнопках
export function showConfirm(title, message, confirmText = 'Удалить', cancelText = 'Отмена') {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'confirm-overlay';

        overlay.innerHTML = `
            <div class="confirm-modal">
                <div class="confirm-title">${escapeHtml(title)}</div>
                <div class="confirm-message">${message}</div>
                <div class="confirm-actions">
                    <button class="confirm-btn confirm-btn-cancel">${escapeHtml(cancelText)}</button>
                    <button class="confirm-btn confirm-btn-confirm">${escapeHtml(confirmText)}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const cancelBtn = overlay.querySelector('.confirm-btn-cancel');
        const confirmBtn = overlay.querySelector('.confirm-btn-confirm');

        const close = (result) => {
            overlay.classList.add('fade-out');
            setTimeout(() => {
                if (overlay.parentNode) overlay.remove();
                resolve(result);
            }, 150);
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