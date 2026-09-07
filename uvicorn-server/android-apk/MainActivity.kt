package com.example.cartridgescanner

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec
import android.util.Base64
import androidx.compose.foundation.layout.Arrangement
import com.example.cartridgescanner.ui.theme.CartridgeScannerTheme
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager



private fun triggerErrorVibration(context: Context) { // Добавили контекст
    val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        val vibratorManager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
        vibratorManager.defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }

    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        // Создаем эффект: 500 мс вибрации на стандартной мощности
        vibrator.vibrate(VibrationEffect.createOneShot(500, VibrationEffect.DEFAULT_AMPLITUDE))
    } else {
        @Suppress("DEPRECATION")
        vibrator.vibrate(500)
    }
}
class MainActivity : ComponentActivity() {
    private val client = OkHttpClient()
    private var isAuthenticated by mutableStateOf(false)

    // хз настолько безопасно так хранить пароли, но и так сойдет
    private val AES_KEY = "My_Secret_Key_16"
    private val APP_PIN = "2033"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            CartridgeScannerTheme(dynamicColor = false) {
                Surface(modifier = Modifier.fillMaxSize()) {
                    if (!isAuthenticated) {
                        // экран ввода пароля
                        LoginScreen(
                            correctPin = APP_PIN,
                            onLoginSuccess = { isAuthenticated = true }
                        )
                    } else {
                        // основной экран сканера
                        ScannerScreen()
                    }
                }
            }
        }
    }

    override fun onStop() {
        super.onStop()
        isAuthenticated = false
    }

    // Экран ввода PIN-кода
    @Composable
    fun LoginScreen(correctPin: String, onLoginSuccess: () -> Unit) {
        var pin by remember { mutableStateOf("") }
        var isError by remember { mutableStateOf(false) }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = 100.dp), // Добавляем отступ только сверху
            verticalArrangement = Arrangement.Top,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("Добро пожаловать!", style = MaterialTheme.typography.headlineSmall)
            Text("Введите код доступа", style = MaterialTheme.typography.headlineSmall)

            Spacer(modifier = Modifier.height(10.dp))

            OutlinedTextField(
                value = pin,
                onValueChange = { newPin ->
                    if (newPin.length <= 4 && newPin.all { it.isDigit() }) {
                        pin = newPin
                        isError = false
                        // Автопроверка при вводе 4 символов
                        if (newPin.length == 4) {
                            if (newPin == correctPin) {
                                onLoginSuccess()
                            } else {
                                isError = true
                                pin = "" // Очистить поле при ошибке
                            }
                        }
                    }
                },
                label = { Text("PIN") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(), // Скрывает цифры точками
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                isError = isError
            )

            if (isError) {
                Spacer(modifier = Modifier.height(8.dp))
                Text("Неверный код!", color = MaterialTheme.colorScheme.error)
            }
        }
    }

    // Основной экран сканера
    @Composable
    fun ScannerScreen() {
        val preferences = remember {
            getSharedPreferences("cartridge_scanner_preferences", MODE_PRIVATE)
        }
        var ipAddress by remember {
            mutableStateOf(preferences.getString("server_ip", "") ?: "")
        }
        var barcode by remember { mutableStateOf("") }
        var action by remember { mutableStateOf("add") }
        var statusText by remember { mutableStateOf("Готов к сканированию") }

        // Для автоматического фокуса
        val focusRequester = remember { FocusRequester() }
        val keyboardController = LocalSoftwareKeyboardController.current
        // Устанавливаем фокус при запуске
        LaunchedEffect(Unit) {
            focusRequester.requestFocus()
            keyboardController?.hide()
        }

        Column(modifier = Modifier.padding(top = 16.dp, start = 20.dp, end = 30.dp)) {
            Text(
                "Cartridge Scanner",
                modifier = Modifier.fillMaxWidth(),
                color = Color.Blue,
                fontSize = 18.sp,
                fontWeight = FontWeight.Medium,
                textAlign = TextAlign.Center
            )

            Spacer(modifier = Modifier.height(4.dp))

            // Поле для IP
            OutlinedTextField(
                value = ipAddress,
                onValueChange = {
                    ipAddress = it
                    preferences.edit().putString("server_ip", it).apply()
                },
                label = { Text("IP веб-сервера") },
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(4.dp))

            // Выбор режима
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    modifier = Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(
                        selected = action == "add",
                        onClick = { action = "add" },
                        modifier = Modifier.padding(0.dp)
                    )
                    Text("Приход", fontSize = 12.sp, fontWeight = FontWeight.Medium)
                }
                Row(
                    modifier = Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(
                        selected = action == "red",
                        onClick = { action = "red" },
                        modifier = Modifier.padding(0.dp)
                    )
                    Text("Расход", fontSize = 12.sp, fontWeight = FontWeight.Medium)
                }
                Row(
                    modifier = Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(
                        selected = action == "getinfo",
                        onClick = { action = "getinfo" },
                        modifier = Modifier.padding(0.dp)
                    )
                    Text("Инфо", fontSize = 12.sp, fontWeight = FontWeight.Medium)
                }
            }

            Spacer(modifier = Modifier.height(4.dp))

            // Поле для сканера
            OutlinedTextField(
                value = barcode,
                onValueChange = { barcode = it },
                label = { Text("Штрих-код:") },
                modifier = Modifier
                    .fillMaxWidth()
                    .focusRequester(focusRequester), // Привязываем фокус
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = {
                    if (barcode.isNotEmpty()) {
                        val serverIp = ipAddress.trim()
                        if (serverIp.isEmpty()) {
                            statusText = "Укажите IP веб-сервера"
                        } else {
                            sendData(serverIp, barcode, action) { result ->
                                statusText = result
                                barcode = "" // Очищаем поле для нового скана
                                focusRequester.requestFocus() // обратно фокус
                                keyboardController?.hide() // скрыть клаву
                            }
                        }
                    }
                })
            )

            Spacer(modifier = Modifier.height(20.dp))

            Text("Статус: $statusText", style = MaterialTheme.typography.bodyLarge)
        }
    }

    // функции шифрования
    private fun encryptAES(data: String): String {
        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        val keySpec = SecretKeySpec(AES_KEY.toByteArray(), "AES")

        cipher.init(Cipher.ENCRYPT_MODE, keySpec)

        val iv = cipher.iv
        val encryptedBytes = cipher.doFinal(data.toByteArray())

        val combined = iv + encryptedBytes
        return Base64.encodeToString(combined, Base64.NO_WRAP)
    }

    private fun decryptAES(encryptedB64: String): String? {
        return try {
            val combined = Base64.decode(encryptedB64, Base64.NO_WRAP)
            val iv = combined.sliceArray(0..15)
            val ciphertext = combined.sliceArray(16 until combined.size)

            val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
            val keySpec = SecretKeySpec(AES_KEY.toByteArray(), "AES")
            val ivSpec = IvParameterSpec(iv)

            cipher.init(Cipher.DECRYPT_MODE, keySpec, ivSpec)

            val decryptedBytes = cipher.doFinal(ciphertext)
            String(decryptedBytes, Charsets.UTF_8)
        } catch (e: Exception) {
            null
        }
    }

    private fun sendData(ip: String, code: String, act: String, onResult: (String) -> Unit) {
        val url = "http://$ip/scan"

        // 1. Генерируем данные для запроса
        val requestId = java.util.UUID.randomUUID().toString()
        val timestamp = System.currentTimeMillis() / 1000

        val rawJson = """
        {
            "barcode": "$code", 
            "action": "$act", 
            "time": $timestamp, 
            "id": "$requestId"
        }
        """.trimIndent()

        // 2. ШИФРУЕМ И СОЗДАЕМ JSON (Проверь эти строки!)
        val encryptedPayload = encryptAES(rawJson)
        val jsonForServer = """{"payload": "$encryptedPayload"}"""

        // 3. Создаем тело запроса и сам запрос
        val body = jsonForServer.toRequestBody("application/json".toMediaTypeOrNull())
        val request = Request.Builder().url(url).post(body).build()

        // 4. Отправляем
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread { onResult("Нет связи!\n${e.localizedMessage}") }
            }

            override fun onResponse(call: Call, response: Response) {
                response.body?.use { responseBodyObj ->
                    val responseBody = responseBodyObj.string()
                    val statusCode = response.code
                    val decryptedMessage = decryptAES(responseBody)

                    runOnUiThread {
                        // Если 404 — вибрируем и выходим
                        if (statusCode == 404) {
                            triggerErrorVibration(this@MainActivity)
                            onResult("Ошибка $statusCode\n$decryptedMessage")
                            return@runOnUiThread
                        }

                        // Если есть зашифрованный ответ от сервера
                        if (decryptedMessage != null) {
                            if (response.isSuccessful) {
                                onResult("Успех $statusCode\n$decryptedMessage")
                            } else {
                                onResult("Ошибка $statusCode\n$decryptedMessage")
                            }
                        } else {
                            // Если сервер прислал не пойми что (например, ошибку 500 в виде HTML)
                            val rawError = if (responseBody.length > 50) responseBody.take(50) + "..." else responseBody
                            onResult("Сбой системы ($statusCode)\n$rawError")
                        }
                    }
                }
            }
        })
    }
}