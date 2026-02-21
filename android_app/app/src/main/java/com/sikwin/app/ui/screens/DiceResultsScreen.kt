package com.sikwin.app.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import com.sikwin.app.ui.theme.*
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

import androidx.compose.runtime.remember
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DiceResultsScreen(
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit
) {
    LaunchedEffect(Unit) {
        viewModel.fetchRecentRoundResults(count = 20)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Recent Dice Results", color = TextWhite, fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = TextWhite)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = BlackBackground)
            )
        },
        containerColor = BlackBackground
    ) { padding ->
        if (viewModel.isLoading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = PrimaryYellow)
            }
        } else if (viewModel.recentResults.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text("No results found", color = TextGrey)
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(viewModel.recentResults) { result ->
                    ResultCard(result)
                }
            }
        }
    }
}

@Composable
fun ResultCard(result: com.sikwin.app.data.models.RecentRoundResult) {
    val formattedTimestamp = remember(result.timestamp) {
        try {
            if (result.timestamp != null) {
                val zonedDateTime = ZonedDateTime.parse(result.timestamp)
                val formatter = DateTimeFormatter.ofPattern("dd MMM yyyy, HH:mm", Locale.getDefault())
                zonedDateTime.format(formatter)
            } else ""
        } catch (e: Exception) {
            result.timestamp ?: ""
        }
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = SurfaceColor
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Round: ${result.round_id}",
                    color = TextGrey,
                    fontSize = 12.sp
                )
                Text(
                    text = formattedTimestamp as String,
                    color = TextGrey,
                    fontSize = 12.sp
                )
            }
            
            Spacer(Modifier.height(12.dp))
            
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val dice = listOf(result.dice_1, result.dice_2, result.dice_3, result.dice_4, result.dice_5, result.dice_6)
                    dice.forEach { value ->
                        DiceIcon(value)
                    }
                }
                
                Column(horizontalAlignment = Alignment.End) {
                    Text("Result", color = TextGrey, fontSize = 10.sp)
                    Text(
                        text = result.dice_result ?: "-",
                        color = PrimaryYellow,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}

@Composable
fun DiceIcon(value: Int?) {
    Surface(
        modifier = Modifier.size(32.dp),
        shape = RoundedCornerShape(4.dp),
        color = Color.White.copy(alpha = 0.1f),
        border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(alpha = 0.2f))
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(
                text = value?.toString() ?: "?",
                color = TextWhite,
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )
        }
    }
}
