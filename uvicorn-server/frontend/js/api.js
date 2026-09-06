/**
 * API.JS
 * Функции для работы с API сервера (GET, POST, PATCH запросы)
 */

/**
 * Сохраняет изменения количества, минимального уровня и имени для картриджа
 * @param {HTMLElement} btn - кнопка "Сохранить" в карточке
 */
async function saveRow(btn) {
    const card = btn.closest('[data-cartridge-id]');
    if (!card) return;

    const cartridgeId = card.dataset.cartridgeId;
    if (!cartridgeId) return;

    const nameInput = card.querySelector('.name-input');
    const qtyInput = card.querySelector('.current-qty');
    const minInput = card.querySelector('.min-qty');
    const reserveInput = card.querySelector('.reserve-qty');
    const timeElement = card.querySelector('.timedate_value');

    if (!nameInput || !qtyInput || !minInput || !reserveInput) return;

    const newName = nameInput.value.trim();
    const newQuantity = parseInt(qtyInput.value, 10) || 0;
    const newMin = parseInt(minInput.value, 10) || 0;
    const newReserve = parseInt(reserveInput.value, 10) || 0;

    if (!newName) {
        alert('Название не может быть пустым!');
        return;
    }

    btn.disabled = true;

    try {
        const response = await fetch(`/api/v1/cartridges/${cartridgeId}/stock`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                new_quantity: newQuantity,
                new_min_qty: newMin,
                new_name: newName,
                new_quantity_reserve: newReserve
            })
        });

        if (!response.ok) {
            console.error('Ошибка при сохранении!');
            alert('Не удалось сохранить изменения. Попробуйте ещё раз.');
            return;
        }

        const data = await response.json();

        if (typeof data.new_stock === 'number') {
            qtyInput.value = data.new_stock;
        }
        if (typeof data.min_qty === 'number') {
            minInput.value = data.min_qty;
        }
        if (typeof data.new_quantity_reserve === 'number') {
            reserveInput.value = data.new_quantity_reserve;
        }
        if (data.last_update && timeElement) {
            timeElement.innerText = data.last_update;
        }

        await updateDashboard();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    } finally {
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
 * Заполняет выпадающий список годов для анализа расходов.
 * Если данных еще нет, все равно оставляем в списке выбранный год.
 *
 * @param {Array<number>} years - доступные годы из истории расходов
 * @param {number} selectedYear - год, который должен быть выбран сейчас
 */
function fillAnalysisYearOptions(years, selectedYear) {
    const yearSelect = document.getElementById('analysisYear');
    if (!yearSelect) return;

    const safeYears = Array.isArray(years) && years.length > 0 ? years : [selectedYear];
    yearSelect.innerHTML = safeYears.map(year => {
        const selectedAttr = Number(year) === Number(selectedYear) ? ' selected' : '';
        return `<option value="${year}"${selectedAttr}>${year}</option>`;
    }).join('');
}

/**
 * Загружает данные для тепловой карты расходов по выбранному году.
 * Учитываются только отрицательные delta из таблицы history.
 */
async function loadExpenseHeatmap() {
    const yearSelect = document.getElementById('analysisYear');
    const buildBtn = document.getElementById('analysisBuildBtn');
    if (!yearSelect) return;

    const selectedYear = parseInt(yearSelect.value, 10) || new Date().getFullYear();

    if (buildBtn) {
        buildBtn.disabled = true;
    }

    try {
        const response = await fetch(`/api/v1/history/expenses/heatmap?year=${selectedYear}`);

        if (!response.ok) {
            console.error('Ошибка при загрузке тепловой карты расходов!');
            alert('Не удалось построить тепловую карту расходов.');
            return;
        }

        const data = await response.json();
        fillAnalysisYearOptions(data.available_years || [], data.selected_year || selectedYear);
        renderExpenseHeatmap(data.series || [], data.selected_year || selectedYear, data.total_spent || 0);
    } catch (error) {
        console.error('Ошибка загрузки тепловой карты:', error);
        alert('Ошибка сети при построении карты расходов.');
    } finally {
        if (buildBtn) {
            buildBtn.disabled = false;
        }
    }
}

/**
 * Загружает данные картриджей с сервера и обновляет все вкладки карточек
 */
async function updateDashboard() {
    try {
        const listSearchInput = document.getElementById('searchInput-1');
        const editorSearchInput = document.getElementById('searchInput-2');
        const deleteSearchInput = document.getElementById('searchInput-3');
        const listSearchValue = listSearchInput ? listSearchInput.value : '';
        const editorSearchValue = editorSearchInput ? editorSearchInput.value : '';
        const deleteSearchValue = deleteSearchInput ? deleteSearchInput.value : '';
        const openedCardIds = Array.from(document.querySelectorAll('#editor-list details[open]')).map(card => card.dataset.cartridgeId);

        const response = await fetch('/api/v1/cartridges');
        const data = await response.json();

        renderSimpleList(data);
        renderEditorList(data);
        renderDeleteList(data);
        initializeEditorCards();

        if (listSearchInput) {
            listSearchInput.value = listSearchValue;
            filterTable_list();
        }

        if (editorSearchInput) {
            editorSearchInput.value = editorSearchValue;
            filterTable_edit();
        }

        if (deleteSearchInput) {
            deleteSearchInput.value = deleteSearchValue;
            filterTable_delete();
        }

        openedCardIds.forEach(id => {
            const card = document.querySelector(`#editor-list details[data-cartridge-id="${id}"]`);
            if (card) {
                card.setAttribute('open', 'open');
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки данных:', error);
    }
}
/**
 * Загружает список email адресов
 */
async function loadEmailList() {
    try {
        const response = await fetch('/api/v1/emails');
        if (!response.ok) {
            console.error('Ошибка при загрузке email списка!');
            return;
        }
        
        const data = await response.json();
        renderEmailList(data.emails);
        
        // Загружаем настройки
        await loadNotificationSettings();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
    }
}

/**
 * Отрисовывает список email адресов
 */
function renderEmailList(emails) {
    const emailList = document.getElementById('emailList');
    if (!emailList) return;
    
    if (!emails || emails.length === 0) {
        emailList.innerHTML = '<p style="padding: 20px; text-align: center; color: var(--muted);">Нет email адресов</p>';
        return;
    }
    
    emailList.innerHTML = emails.map(email => `
        <div class="email-item">
            <span class="email-address">${email.email_address}</span>
            <label class="email-checkbox">
                <input type="checkbox" 
                       ${email.notifications_on ? 'checked' : ''} 
                       onchange="toggleEmailNotifications(${email.id}, this.checked)">
                В рассылке
            </label>
            <button class="delete-email-btn" onclick="deleteEmail(${email.id})">Удалить</button>
        </div>
    `).join('');
}

/**
 * Добавляет новый email адрес
 */
async function addEmail() {
    const input = document.getElementById('newEmailInput');
    const btn = document.getElementById('addEmailBtn');
    if (!input || !btn) return;
    
    const email = input.value.trim();
    if (!email) {
        alert('Введите email адрес');
        return;
    }
    
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/v1/emails', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email_address: email })
        });
        
        if (!response.ok) {
            const error = await response.json();
            alert(error.detail || 'Ошибка при добавлении email');
            return;
        }
        
        input.value = '';
        await loadEmailList();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    } finally {
        btn.disabled = false;
    }
}

/**
 * Включает/выключает уведомления для email
 */
async function toggleEmailNotifications(emailId, enabled) {
    try {
        const response = await fetch(`/api/v1/emails/${emailId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ notifications_on: enabled })
        });
        
        if (!response.ok) {
            console.error('Ошибка при обновлении настроек уведомлений!');
            alert('Не удалось обновить настройки. Попробуйте ещё раз.');
            return;
        }
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    }
}

/**
 * Удаляет email адрес
 */
async function deleteEmail(emailId) {
    if (!confirm('Вы уверены, что хотите удалить этот email адрес?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/v1/emails/${emailId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            console.error('Ошибка при удалении email!');
            alert('Не удалось удалить email. Попробуйте ещё раз.');
            return;
        }
        
        await loadEmailList();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    }
}

/**
 * Отправляет тестовое уведомление
 */
async function sendTestNotification() {
    const btn = document.getElementById('sendTestNotification');
    if (!btn) return;
    
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/v1/emails/send-notifications', {
            method: 'POST'
        });
        
        if (!response.ok) {
            console.error('Ошибка при отправке уведомлений!');
            alert('Не удалось отправить уведомления. Проверьте настройки.');
            return;
        }
        
        const data = await response.json();
        alert(data.message);
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    } finally {
        btn.disabled = false;
    }
}

/**
 * Включает/выключает рассылку уведомлений (глобальная настройка)
 */
async function toggleNotifications() {
    const checkbox = document.getElementById('enableNotifications');
    if (!checkbox) return;
    
    const enabled = checkbox.checked;
    
    try {
        const response = await fetch('/api/v1/notifications-enabled', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ enabled: enabled })
        });
        
        if (!response.ok) {
            const error = await response.json();
            console.error('Ошибка при сохранении настройки уведомлений:', error);
            alert('Ошибка: ' + (error.detail || 'Не удалось сохранить настройку.'));
            // Возвращаем чекбокс в предыдущее состояние
            checkbox.checked = !enabled;
            return;
        }
        
        const data = await response.json();
        console.log(data.message);
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
        // Возвращаем чекбокс в предыдущее состояние
        checkbox.checked = !enabled;
    }
}

/**
 * Загружает настройки уведомлений
 */
async function loadNotificationSettings() {
    try {
        const response = await fetch('/api/v1/notification-schedule');
        if (response.ok) {
            const data = await response.json();
            const timeInput = document.getElementById('notificationTime');
            
            // Сбрасываем все чек-боксы дней
            for (let i = 0; i <= 6; i++) {
                const checkbox = document.getElementById(`day-${i}`);
                if (checkbox) checkbox.checked = false;
            }
            
            // Если есть дни, отмечаем соответствующие чек-боксы
            if (data.days_of_week) {
                const days = data.days_of_week.split(',').map(d => parseInt(d.trim(), 10));
                days.forEach(day => {
                    const checkbox = document.getElementById(`day-${day}`);
                    if (checkbox) checkbox.checked = true;
                });
            }
            
            if (timeInput && data.time_hm) {
                timeInput.value = data.time_hm;
            }
        }
        
        // Загружаем статус глобальной настройки
        const enabledResponse = await fetch('/api/v1/notifications-enabled');
        if (enabledResponse.ok) {
            const enabledData = await enabledResponse.json();
            const enableCheckbox = document.getElementById('enableNotifications');
            if (enableCheckbox) {
                enableCheckbox.checked = enabledData.enabled;
            }
        }
    } catch (error) {
        console.error('Ошибка загрузки настроек:', error);
    }
}

/**
 * Сохраняет дни недели и время для уведомлений
 */
async function saveNotificationSchedule() {
    const timeInput = document.getElementById('notificationTime');
    
    if (!timeInput) return;
    
    // Собираем выбранные дни
    const selectedDays = [];
    for (let i = 0; i <= 6; i++) {
        const checkbox = document.getElementById(`day-${i}`);
        if (checkbox && checkbox.checked) {
            selectedDays.push(i);
        }
    }
    
    const daysString = selectedDays.join(',');
    const time = timeInput.value;
    
    // Проверяем, что время введено полностью (в формате ЧЧ:ММ)
    if (!time || !/^([01]?[0-9]|2[0-3]):[0-5][0-9]$/.test(time)) {
        // Не показываем alert, просто игнорируем неполное время
        return;
    }
    
    // Проверяем, что выбран хотя бы один день
    if (selectedDays.length === 0) {
        alert('Выберите хотя бы один день недели для рассылки.');
        return;
    }
    
    try {
        const response = await fetch('/api/v1/notification-schedule', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                days_of_week: daysString, 
                time_hm: time 
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            console.error('Ошибка при сохранении расписания!', error);
            alert('Ошибка: ' + (error.detail || 'Не удалось сохранить расписание.'));
            return;
        }
        
        alert('Расписание сохранено. Уведомления будут отправляться в ' + time + ' по выбранным дням.');
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    }
}

/**
 * Добавляет новый картридж в базу данных
 */
async function addNewCartridge() {
    const nameInput = document.getElementById('addCartridgeName');
    const qtyInput = document.getElementById('addCartridgeQuantity');
    const minQtyInput = document.getElementById('addCartridgeMinQty');
    const reserveQtyInput = document.getElementById('addCartridgeReserveQuantity');
    const barcodeInput = document.getElementById('addCartridgeBarcode');

    if (!nameInput || !qtyInput || !minQtyInput || !reserveQtyInput || !barcodeInput) {
        alert('Не удалось найти поля формы');
        return;
    }

    const name = nameInput.value.trim();
    const quantity = parseInt(qtyInput.value, 10) || 0;
    const minQty = parseInt(minQtyInput.value, 10) || 1;
    const reserveQty = parseInt(reserveQtyInput.value, 10) || 0;
    const barcode = barcodeInput.value.trim();

    // Валидация
    if (!name) {
        alert('Введите название картриджа');
        return;
    }

    if (reserveQty < 0) {
        alert('Резервное количество не может быть отрицательным');
        return;
    }

    if (minQty < 1) {
        alert('Минимальный остаток должен быть не менее 1');
        return;
    }

    if (!barcode) {
        alert('Введите штрих-код');
        return;
    }

    if (!/^\d{13}$/.test(barcode)) {
        alert('Штрих-код должен состоять ровно из 13 цифр');
        return;
    }

    if (quantity < 0) {
        alert('Количество не может быть отрицательным');
        return;
    }

    try {
        const response = await fetch('/api/v1/cartridges', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                cartridge_name: name,
                quantity: quantity,
                min_qty: minQty,
                quantity_reserve: reserveQty,
                barcode: barcode
            })
        });

        if (!response.ok) {
            const error = await response.json();
            alert('Ошибка: ' + (error.detail || 'Не удалось добавить картридж'));
            return;
        }

        const result = await response.json();
        
        // Очищаем форму
        nameInput.value = '';
        qtyInput.value = '0';
        minQtyInput.value = '1';
        reserveQtyInput.value = '0';
        barcodeInput.value = '';

        alert('Картридж успешно добавлен');

        // Обновляем данные
        await updateDashboard();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    }
}

/**
 * Удаляет картридж из базы данных
 * @param {HTMLElement} btn - кнопка "Удалить"
 */
async function deleteCartridge(btn) {
    const card = btn.closest('[data-cartridge-id]');
    if (!card) return;

    const cartridgeId = card.dataset.cartridgeId;
    const cartridgeName = card.dataset.cartridgeName || 'Неизвестный картридж';

    if (!cartridgeId) return;

    // Запрашиваем подтверждение
    if (!confirm(`Вы действительно хотите удалить картридж "${cartridgeName}"?\n\nЭто действие необратимо. Все штрих-коды будут удалены.`)) {
        return;
    }

    btn.disabled = true;

    try {
        const response = await fetch(`/api/v1/cartridges/${cartridgeId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            alert('Ошибка: ' + (error.detail || 'Не удалось удалить картридж'));
            return;
        }

        alert('Картридж успешно удален');

        // Обновляем данные
        await updateDashboard();
    } catch (error) {
        console.error('Сетевая ошибка:', error);
        alert('Ошибка сети. Проверьте подключение и попробуйте ещё раз.');
    } finally {
        btn.disabled = false;
    }
}