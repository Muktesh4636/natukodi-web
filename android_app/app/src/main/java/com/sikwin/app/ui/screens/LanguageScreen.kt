package com.sikwin.app.ui.screens

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.sp
import androidx.core.os.LocaleListCompat
import com.sikwin.app.R
import androidx.appcompat.app.AppCompatDelegate
import com.sikwin.app.data.prefs.LanguagePreferences
import com.sikwin.app.ui.theme.*

data class LanguageOption(val tag: String, val displayName: String)

@Composable
fun LanguageScreen(
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val activity = context as? Activity
    val languagePrefs = remember { LanguagePreferences(context) }
    val currentLocale = remember { languagePrefs.getAppLocale() }

    val languages = listOf(
        LanguageOption("en", stringResource(R.string.lang_name_english)),
        LanguageOption("te", stringResource(R.string.lang_name_telugu)),
        LanguageOption("hi", stringResource(R.string.lang_name_hindi))
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
    ) {
        // Header
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            IconButton(
                onClick = onBack,
                modifier = Modifier.align(Alignment.CenterStart)
            ) {
                Icon(
                    Icons.Default.ArrowBack,
                    contentDescription = "Back",
                    tint = TextWhite,
                    modifier = Modifier.size(28.dp)
                )
            }
            Text(
                stringResource(R.string.languages),
                color = PrimaryYellow,
                fontSize = 20.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.align(Alignment.Center)
            )
        }

        Text(
            stringResource(R.string.choose_language),
            color = TextGrey,
            fontSize = 14.sp,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
        )

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(16.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(SurfaceColor)
        ) {
            languages.forEach { option ->
                val isSelected = currentLocale == option.tag
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable {
                            languagePrefs.setAppLocale(option.tag)
                            AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(option.tag))
                            activity?.recreate()
                        }
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        option.displayName,
                        color = TextWhite,
                        fontSize = 16.sp,
                        modifier = Modifier.weight(1f)
                    )
                    if (isSelected) {
                        Icon(
                            Icons.Default.Check,
                            contentDescription = null,
                            tint = PrimaryYellow,
                            modifier = Modifier.size(24.dp)
                        )
                    }
                }
            }
        }
    }
}
