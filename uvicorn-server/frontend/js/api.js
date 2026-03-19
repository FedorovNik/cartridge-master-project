/**
 * API.JS
 * Функции для работы с API сервера (GET, POST, PATCH запросы)
 */

/**
 * Обновляет количество картриджей (отправляет PATCH запрос на сервер)
 * @param {HTMLElement} btn - кнопка, которая была нажата
 * @param {number} cartridgeId - ID картриджа
 * @param {number} delta - изменение количества (+1 или -1)
 */
async function changeQty(btn, cartridgeId, delta) {
    // Находим общую строку (tr), в которой находится нажатая кнопка
    const row = btn.closest('tr');
    // Ищем внутри этой строки элемент с количеством и элемент со временем
    const stockElement = row.querySelector('.qty-value');
    const timeElement = row.querySelector('.timedate_value');
    
    // Блокируем кнопку чтобы не было двойных кликов пока идет запрос
    btn.disabled = true;

    try {
        const response = await fetch(`/api/v1/cartridges/${cartridgeId}/stock`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ change: delta }) 
        });

        if (response.ok) {
            const data = await response.json();
            // Обновляем цифру количества
            stockElement.innerText = data.new_stock;
            // Обновляем время (проверяем, прислал ли сервер новое время, 
            // так как при уходе в минус сервер возвращает только new_stock)
            if (data.last_update) {
                timeElement.innerText = data.last_update;
            }
            else {
                console.error('Пусто');
            }
            
        } else {
            console.error('Ошибка при обновлении количества!');
            alert('Не удалось обновить базу данных!');
        }
    } catch (error) {
        console.error('Сетевая ошибка:', error);
    } finally {
        // Разблокируем кнопку
        btn.disabled = false;
    }
}

/**
 * Загружает данные картриджей с сервера и обновляет обе таблицы
 */
async function updateDashboard() {
    try {
        const response = await fetch('/api/v1/cartridges');
        const data = await response.json();

        // Заполняем обе таблицы разными функциями
        renderSimpleList(data);
        renderEditorList(data);
    } catch (error) {
        console.error('Ошибка загрузки данных:', error);
    }
}
