function showSection(sectionId, clickedBtn) {
    updateDashboard();
    // Скрываем все секции
    const sections = document.querySelectorAll('.content-section');
    sections.forEach(sec => sec.classList.remove('active-section'));

    // Убираем выделение (класс active) со всех кнопок меню
    const buttons = document.querySelectorAll('.nav-btn');
    buttons.forEach(btn => btn.classList.remove('active'));

    // Показываем нужную секцию
    document.getElementById(sectionId).classList.add('active-section');

    // Делаем нажатую кнопку активной
    clickedBtn.classList.add('active');
    
}

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
function filterTable_list() {
    // Получаем то, что ввел пользователь, и переводим в нижний регистр
    const searchValue = document.getElementById('searchInput-1').value.toLowerCase();
    
    // Получаем все строки таблицы
    const rows = document.querySelectorAll('#inv-table tbody tr');

    rows.forEach(row => {
        // Берем конкретно вторую ячейку (td) в строке, где лежит имя
        const nameCell = row.cells[1]; 
        
        // На всякий случай проверяем, есть ли ячейка чтобы не было ошибок на пустых строках
        if (nameCell) {
            // Берем текст только из ячейки с именем
            const nameText = nameCell.textContent.toLowerCase();
            if (nameText.includes(searchValue)) {
                row.style.display = ''; 
            } else {
                row.style.display = 'none'; 
            }
        }
    });
}

function filterTable_edit() {
    // Получаем то, что ввел пользователь, и переводим в нижний регистр
    const searchValue = document.getElementById('searchInput-2').value.toLowerCase();
    
    // Получаем все строки таблицы
    const rows = document.querySelectorAll('#editor-table tbody tr');

    rows.forEach(row => {
        // Берем конкретно вторую ячейку (td) в строке, где лежит имя
        const nameCell = row.cells[1]; 
        
        // На всякий случай проверяем, есть ли ячейка чтобы не было ошибок на пустых строках
        if (nameCell) {
            // Берем текст только из ячейки с именем
            const nameText = nameCell.textContent.toLowerCase();
            if (nameText.includes(searchValue)) {
                row.style.display = ''; 
            } else {
                row.style.display = 'none'; 
            }
        }
    });
}


// Главная функция обновления, которую вызываем при загрузке и по таймеру
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

// ФУНКЦИЯ 1: Просто список с подсветкой критического остатка
function renderSimpleList(data) {
    const tbody = document.querySelector('#inv-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    data.forEach(item => {
        // Проверка: если количество меньше минимума — добавляем класс 'low-stock'
        const isLow = item.quantity < item.min_qty;
        const qtyClass = isLow ? 'qty-value low-stock' : 'qty-value';

        const row = `<tr>
            <td>${item.id}</td>
            <td>${item.name}</td>
            <td><span class="${qtyClass}">${item.quantity}</span></td>
            <td>${item.min_qty}</td>
            
            <td>${item.last_update}</td>
        </tr>`;
        tbody.innerHTML += row;
        //<td>${item.barcodes.map(b => `<span class="barcode-badge">${b}</span>`).join('')}</td>
    });
}

// ФУНКЦИЯ 2: Редактор с кнопками +/- 
function renderEditorList(data) {
    const tbody = document.querySelector('#editor-table tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    data.forEach(item => {
        const row = `<tr>
            <td>${item.id}</td>
            <td>${item.name}</td>
            <td>
                <div class="qty-controls">
                    <button class="qty-btn" onclick="changeQty(this, ${item.id}, -1)">-</button>
                    <span class="qty-value">${item.quantity}</span>
                    <button class="qty-btn" onclick="changeQty(this, ${item.id}, 1)">+</button>
                </div>
            </td>
            <td>${item.min_qty}</td>
            <td>${item.barcodes.map(b => `<span class="barcode-badge">${b}</span>`).join('')}</td>
            <td><span class="timedate_value">${item.last_update}</span></td>
        </tr>`;
        tbody.innerHTML += row;
    });
}



// Вызов при загрузке страницы
window.onload = updateDashboard;
//updateDashboard();
//setInterval(updateDashboard, 5000);