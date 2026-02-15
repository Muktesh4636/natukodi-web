package com.sikwin.app.data.api

import com.sikwin.app.data.auth.SessionManager
import com.sikwin.app.utils.Constants
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object RetrofitClient {
    private const val BASE_URL = Constants.BASE_URL
    private var sessionManager: SessionManager? = null

    fun init(manager: SessionManager) {
        sessionManager = manager
    }

    fun getSessionManager(): SessionManager? = sessionManager

    private val logging = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .writeTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .addInterceptor(logging)
        .addInterceptor { chain ->
            val requestBuilder = chain.request().newBuilder()
            sessionManager?.fetchAuthToken()?.let {
                requestBuilder.addHeader("Authorization", "Bearer $it")
            }
            chain.proceed(requestBuilder.build())
        }
        .authenticator { _, response ->
            // This runs when we get a 401 Unauthorized
            if (response.code == 401) {
                val refreshToken = sessionManager?.fetchRefreshToken()
                if (refreshToken != null) {
                    // Try to refresh the token synchronously
                    val refreshResponse = try {
                        // We need a separate retrofit instance or service for refresh to avoid infinite loops
                        val refreshService = Retrofit.Builder()
                            .baseUrl(BASE_URL)
                            .addConverterFactory(GsonConverterFactory.create())
                            .build()
                            .create(ApiService::class.java)

                        // Use runBlocking for synchronous call in authenticator
                        kotlinx.coroutines.runBlocking {
                            refreshService.refreshToken(mapOf("refresh" to refreshToken))
                        }
                    } catch (e: Exception) {
                        null
                    }

                    if (refreshResponse?.isSuccessful == true) {
                        val newAccessToken = refreshResponse.body()?.get("access")
                        if (newAccessToken != null) {
                            sessionManager?.saveAuthToken(newAccessToken)
                            // Sync to Unity as well
                            sessionManager?.syncAuthToUnity()

                            // Retry the request with the new token
                            return@authenticator response.request.newBuilder()
                                .header("Authorization", "Bearer $newAccessToken")
                                .build()
                        }
                    } else {
                        // Refresh failed - session really expired
                        android.util.Log.e("RetrofitClient", "Refresh token expired or invalid")
                        // We can't call viewModel.logout() here directly easily
                        // But we can clear the session manager
                        sessionManager?.logout()
                    }
                } else {
                    // No refresh token
                    sessionManager?.logout()
                }
            }
            null
        }
        .build()

    val apiService: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .client(client)
            .build()
            .create(ApiService::class.java)
    }
}
