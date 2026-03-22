/**
 * API.JS
 * Функции для работы с API сервера (GET, POST, PATCH запросы)
 */

/**
 * Сохраняет изменения количества, минимального уровня и имени для картриджа
 * @param {HTMLElement} btn - кнопка "Сохранить" в строке
 */
async function saveRow(btn) {
    // Находим строку таблицы
    const row = btn.closest('tr');
    if (!row) return;

    // Получаем ID картриджа из data-атрибута
    const cartridgeId = row.dataset.cartridgeId;
    if (!cartridgeId) return;

    // Находим элементы ввода
    const nameInput = row.querySelector('.name-input');
    const qtyInput = row.querySelector('.current-qty');
    const minInput = row.querySelector('.min-qty');
    const timeElement = row.querySelector('.timedate_value');

    if (!nameInput || !qtyInput || !minInput) return;

    // Получаем и валидируем значения
    const newName = nameInput.value.trim();
    const newQuantity = parseInt(qtyInput.value, 10) || 0;
    const newMin = parseInt(minInput.value, 10) || 0;

    // Проверяем, что имя не пустое
    if (!newName) {
        alert('Название не может быть пустым!');
        return;
    }

    // Отключаем кнопку, чтобы предотвратить повторные клики
    btn.disabled = true;

    try {
        // Отправляем PATCH запрос на сервер с новыми значениями
        // Эта строка отправляет объект с новыми quantity, min_qty и name для обновления на сервере
        const response = await fetch(`/api/v1/cartridges/${cartridgeId}/stock`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                new_quantity: newQuantity,
                new_min_qty: newMin,
                new_name: newName
            })
        });

        if (!response.ok) {
            console.error('Ошибка при сохранении!');
            alert('Не удалось сохранить изменения. Попробуйте ещё раз.');
            return;
        }

        // Получаем обновленные данные от сервера
        const data = await response.json();

        // Обновляем поля ввода актуальными значениями
        if (typeof data.new_stock === 'number') {
            qtyInput.value = data.new_stock;
        }
        if (typeof data.min_qty === 'number') {
            minInput.value = data.min_qty;
        }
        if (data.last_update && timeElement) {
            timeElement.innerText = data.last_update;
        }

        // Обновляем всю таблицу для корректности подсветки и данных
        await updateDashboard();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    } finally {
        // Включаем кнопку обратно
        btn.disabled = false;
    }
}

/**
 * Удаляет штрих-код у картриджа
 * @param {HTMLElement} btn - кнопка минус
 * @param {string} barcode - штрих-код для удаления
 */
async function removeBarcode(btn, barcode) {
    const cell = btn.closest('.barcodes-cell');
    if (!cell) return;

    const cartridgeId = cell.dataset.cartridgeId;
    if (!cartridgeId) return;

    btn.disabled = true;
    try {
        const response = await fetch(`/api/v1/cartridges/${cartridgeId}/barcodes/${encodeURIComponent(barcode)}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            console.error('Ошибка при удалении штрих-кода!');
            alert('Не удалось удалить штрих-код. Попробуйте ещё раз.');
            return;
        }

        // Обновляем таблицу
        await updateDashboard();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    } finally {
        btn.disabled = false;
    }
}

/**
 * Добавляет новый штрих-код к картриджу
 * @param {HTMLElement} btn - кнопка "Добавить"
 */
async function addBarcode(btn) {
    const cell = btn.closest('.barcodes-cell');
    if (!cell) return;

    const cartridgeId = cell.dataset.cartridgeId;
    const input = cell.querySelector('.new-barcode-input');
    if (!cartridgeId || !input) return;

    const newBarcode = input.value.trim();
    if (!newBarcode) {
        alert('Введите штрих-код!');
        return;
    }

    if (!/^\d{13}$/.test(newBarcode)) {
        alert('Штрих-код должен состоять ровно из 13 цифр!');
        return;
    }

    btn.disabled = true;
    try {
        const response = await fetch(`/api/v1/cartridges/${cartridgeId}/barcodes`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ barcode: newBarcode })
        });

        if (!response.ok) {
            console.error('Ошибка при добавлении штрих-кода!');
            alert('Не удалось добавить штрих-код.\n99% что он уже есть в базе.');
            return;
        }

        input.value = ''; // Очищаем поле
        // Обновляем таблицу
        await updateDashboard();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    } finally {
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

        // Очищаем поля поиска
        document.getElementById('searchInput-1').value = '';
        document.getElementById('searchInput-2').value = '';

        // Заполняем обе таблицы разными функциями
        renderSimpleList(data);
        renderEditorList(data);
    } catch (error) {
        console.error('Ошибка загрузки данных:', error);
    }
}
