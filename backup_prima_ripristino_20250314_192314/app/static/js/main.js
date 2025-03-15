/**
 * Script principale per il Generatore di Corsi AI
 */
document.addEventListener('DOMContentLoaded', function() {
    // Inizializza i tooltips di Bootstrap (se presenti)
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    if (tooltipTriggerList.length > 0) {
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }

    // Gestione degli elementi collassabili (se presenti)
    const collapsibleElements = document.querySelectorAll('.collapsible-trigger');
    collapsibleElements.forEach(element => {
        element.addEventListener('click', function() {
            const targetId = this.getAttribute('data-target');
            const targetElement = document.getElementById(targetId);
            
            if (targetElement) {
                if (targetElement.classList.contains('d-none')) {
                    targetElement.classList.remove('d-none');
                    targetElement.classList.add('fade-in');
                    this.innerHTML = this.getAttribute('data-collapse-text') || 'Nascondi';
                } else {
                    targetElement.classList.add('d-none');
                    this.innerHTML = this.getAttribute('data-expand-text') || 'Mostra';
                }
            }
        });
    });

    // Funzione per mostrare notifiche
    window.showNotification = function(message, type = 'info') {
        const notificationArea = document.getElementById('notification-area');
        if (!notificationArea) return;
        
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show`;
        notification.role = 'alert';
        
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        notificationArea.appendChild(notification);
        
        // Auto-dismissione dopo 5 secondi
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                notificationArea.removeChild(notification);
            }, 300);
        }, 5000);
    };
}); 