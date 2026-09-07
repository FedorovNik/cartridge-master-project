/**
 * AUTH.JS
 * Проверка аутентификации, выход из системы и обработка формы логина
 */

// Проверяем сессию при загрузке страницы
window.addEventListener('DOMContentLoaded', function() {
    checkAuth();
});

async function checkAuth() {
    try {
        const response = await fetch('/api/v1/me');
        if (!response.ok) {
            if (window.location.pathname !== '/admin-ui/pages/login.html') {
                window.location.href = '/admin-ui/pages/login.html';
            }
            return;
        }
        // Получаем имя пользователя и отображаем его в верхней панели
        const data = await response.json();
        //const username = data.user_dn ? data.user_dn.split('@')[0] : '';
        const username = data.user_dn || '';
        const userElement = document.getElementById('mainUsername');
        if (userElement) {
            userElement.textContent = username || 'Неизвестен';
        }
        
        // Показываем контент после успешной проверки
        showContent();
    } catch (error) {
        console.error('Ошибка проверки аутентификации:', error);
        if (window.location.pathname !== '/admin-ui/pages/login.html') {
            window.location.href = '/admin-ui/pages/login.html';
        }
    }
}
// Возвращаем прозрачность body к 1 после загрузки данных, чтобы избежать мерцания левого сайдбара
function showContent() {
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.style.display = 'none';
    }
    document.body.style.opacity = '1';
}
// Для выхода из системы, потом перенести по нормальному в api
async function logout() {
    try {
        await fetch('/api/v1/logout', {
            method: 'POST'
        });
    } catch (error) {
        console.error('Ошибка при выходе:', error);
    }
    // В любом случае перенаправляем на логин
    window.location.href = '/admin-ui/pages/login.html';
}

function switchAuthTab(authType) {
    // Обновляем активную кнопку
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Обновляем скрытое поле с типом авторизации
    document.getElementById('authType').value = authType;
    
    // Очищаем ошибки при смене способа авторизации
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.style.display = 'none';
    errorDiv.textContent = '';
}
// Обработчик отправки формы логина
document.getElementById('loginForm')?.addEventListener('submit', async function(e) {
    e.preventDefault();
    // Собираем данные с формы
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const authType = document.getElementById('authType').value;
    const errorDiv = document.getElementById('errorMessage');
    // Пробуем отправить post на сервер для авторизации
    try {
        const response = await fetch('/api/v1/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: username,
                password: password,
                auth_type: authType
            })
        });
        // Перенаправляем на главную страницу или показываем ошибку
        if (response.ok) {
            window.location.href = '/admin-ui/pages/index.html';
        } else {
            const error = await response.text();
            errorDiv.textContent = 'Неверные учётные данные';
            errorDiv.style.display = 'block';
        }
    // Обработка ошибок сети или других проблем при запросе
    } catch (error) {
        console.error('Ошибка:', error);
        errorDiv.textContent = 'Ошибка сети. Попробуйте ещё раз.';
        errorDiv.style.display = 'block';
    }
});