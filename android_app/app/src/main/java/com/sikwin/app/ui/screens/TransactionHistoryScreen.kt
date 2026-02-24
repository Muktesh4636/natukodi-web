package com.sikwin.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.*
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.stringResource
import com.sikwin.app.R
import com.sikwin.app.data.models.DepositRequest
import com.sikwin.app.data.models.WithdrawRequest
import com.sikwin.app.ui.theme.*
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionHistoryScreen(
    title: String = "Transaction Record",
    initialCategory: String = "Betting",
    showTabs: Boolean = true,
    viewModel: GunduAtaViewModel,
    onBack: () -> Unit
) {
    // Main Categories: Deposit, Withdraw, Betting
    var selectedCategory by remember { mutableStateOf(initialCategory) }
    val categories = listOf("Deposit", "Withdraw", "Betting")

    // Sub-filters for Deposit/Withdraw: All, Success, Failed
    var selectedFilter by remember { mutableStateOf("All") }
    val filters = listOf("All", "Success", "Failed")

    // Date Picker State
    val dateRangePickerState = rememberDateRangePickerState()
    var showDatePicker by remember { mutableStateOf(false) }

    if (showDatePicker) {
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = { showDatePicker = false }) {
                    Text(stringResource(R.string.ok), color = PrimaryYellow)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) {
                    Text(stringResource(R.string.cancel), color = TextGrey)
                }
            },
            colors = DatePickerDefaults.colors(
                containerColor = SurfaceColor,
            )
        ) {
            DateRangePicker(
                state = dateRangePickerState,
                colors = DatePickerDefaults.colors(
                    containerColor = SurfaceColor,
                )
            )
        }
    }

    LaunchedEffect(selectedCategory) {
        when (selectedCategory) {
            "Betting" -> viewModel.fetchBettingHistory()
            "Deposit" -> viewModel.fetchDeposits()
            "Withdraw" -> viewModel.fetchWithdrawals()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
    ) {
        // Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, null, tint = PrimaryYellow, modifier = Modifier.size(32.dp))
            }
            Text(
                title,
                color = PrimaryYellow,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center
            )
            // Functionality for this icon can be added later or removed if not needed
            Icon(Icons.Default.FilterList, null, tint = Color.Transparent, modifier = Modifier.size(28.dp))
        }

        // Main Category Tabs
        if (showTabs) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                categories.forEach { category ->
                    HistoryTab(category, selectedCategory == category) {
                        selectedCategory = category
                        selectedFilter = "All" // Reset filter when changing category
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Sub-filters (Only for Deposit and Withdraw)
        if (selectedCategory != "Betting") {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                filters.forEach { filter ->
                    FilterChip(
                        selected = selectedFilter == filter,
                        onClick = { selectedFilter = filter },
                        label = { Text(filter) },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = PrimaryYellow,
                            selectedLabelColor = BlackBackground,
                            containerColor = SurfaceColor,
                            labelColor = TextGrey
                        ),
                        border = FilterChipDefaults.filterChipBorder(
                            enabled = true,
                            selected = selectedFilter == filter,
                            borderColor = if (selectedFilter == filter) PrimaryYellow else TextGrey
                        )
                    )
                }
            }
        }

        /* Date Filter Removed */
        /*
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Surface(
                color = SurfaceColor,
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier
                    .weight(1f)
                    .clickable { showDatePicker = true }
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(Icons.Default.History, null, tint = TextGrey, modifier = Modifier.size(20.dp))
                    Spacer(modifier = Modifier.width(8.dp))

                    val startDateText = dateRangePickerState.selectedStartDateMillis?.let { convertMillisToDate(it) } ?: "Start Date"
                    val endDateText = dateRangePickerState.selectedEndDateMillis?.let { convertMillisToDate(it) } ?: "End Date"
                    val displayText = if (dateRangePickerState.selectedStartDateMillis != null) "$startDateText-$endDateText" else "Select Date Range"

                    Text(displayText, color = TextWhite, fontSize = 14.sp)
                }
            }
            Spacer(modifier = Modifier.width(12.dp))
            Button(
                onClick = { /* Search logic */ },
                colors = ButtonDefaults.buttonColors(containerColor = SurfaceColor),
                shape = RoundedCornerShape(20.dp),
                border = BorderStroke(1.dp, BorderColor)
            ) {
                Text(stringResource(R.string.search), color = TextGrey)
            }
        }
        */

        // Data Filtering Logic
        val filteredDeposits = remember(viewModel.depositRequests, selectedFilter) {
            when (selectedFilter) {
                "Success" -> viewModel.depositRequests.filter { it.status == "APPROVED" }
                "Failed" -> viewModel.depositRequests.filter { it.status == "REJECTED" }
                else -> viewModel.depositRequests
            }
        }

        val filteredWithdrawals = remember(viewModel.withdrawRequests, selectedFilter) {
            when (selectedFilter) {
                "Success" -> viewModel.withdrawRequests.filter { it.status == "APPROVED" }
                "Failed" -> viewModel.withdrawRequests.filter { it.status == "REJECTED" }
                else -> viewModel.withdrawRequests
            }
        }

        val itemsCount = when (selectedCategory) {
            "Betting" -> viewModel.bettingHistory.size
            "Deposit" -> filteredDeposits.size
            "Withdraw" -> filteredWithdrawals.size
            else -> 0
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.End
        ) {
            Text(stringResource(R.string.summary), color = TextWhite, fontSize = 14.sp)
            Text("$itemsCount", color = GreenSuccess, fontSize = 14.sp, fontWeight = FontWeight.Bold)
        }

        // List Content
        if (viewModel.isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = PrimaryYellow)
            }
        } else if (itemsCount > 0) {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                when (selectedCategory) {
                    "Betting" -> {
                        items(viewModel.bettingHistory.size) { index ->
                            val bet = viewModel.bettingHistory[index]
                            val outcome = if (bet.is_winner) "WIN (₹${bet.payout_amount})" else "LOSE"
                            val color = if (bet.is_winner) GreenSuccess else Color.Red
                            
                            BettingItem(
                                roundId = bet.round.round_id,
                                number = bet.number.toString(),
                                amount = bet.chip_amount,
                                status = outcome,
                                statusColor = color,
                                date = bet.created_at
                            )
                        }
                    }
                    "Deposit" -> {
                        items(filteredDeposits.size) { index ->
                            val dep = filteredDeposits[index]
                            DepositItem(dep = dep)
                        }
                    }
                    "Withdraw" -> {
                        items(filteredWithdrawals.size) { index ->
                            val wd = filteredWithdrawals[index]
                            WithdrawItem(wd = wd)
                        }
                    }
                }
            }
        } else {
            Column(
                modifier = Modifier.fillMaxSize(),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                Text(stringResource(R.string.no_data_available), color = TextGrey, fontSize = 16.sp)
            }
        }
    }
}

@Composable
fun DepositItem(dep: DepositRequest) {
    val isRejected = dep.status == "REJECTED"
    val hasRejectionNote = !dep.admin_note.isNullOrBlank()
    Surface(
        color = SurfaceColor,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "Deposit #${dep.id} (${dep.status})",
                        color = if (isRejected) Color.Red else TextWhite,
                        fontWeight = FontWeight.Bold
                    )
                    Text(dep.created_at, color = TextGrey, fontSize = 12.sp)
                }
                Spacer(modifier = Modifier.width(16.dp))
                Text(
                    text = "₹ ${dep.amount}",
                    color = PrimaryYellow,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.widthIn(min = 80.dp),
                    textAlign = androidx.compose.ui.text.style.TextAlign.End
                )
            }
            if (isRejected && hasRejectionNote) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = dep.admin_note!!,
                    color = TextGrey,
                    fontSize = 13.sp,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}

@Composable
fun WithdrawItem(wd: WithdrawRequest) {
    val isRejected = wd.status == "REJECTED"
    val hasRejectionNote = !wd.admin_note.isNullOrBlank()
    Surface(
        color = SurfaceColor,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "Withdrawal #${wd.id} (${wd.status})",
                        color = if (isRejected) Color.Red else TextWhite,
                        fontWeight = FontWeight.Bold
                    )
                    Text(wd.created_at, color = TextGrey, fontSize = 12.sp)
                }
                Spacer(modifier = Modifier.width(16.dp))
                Text(
                    text = "₹ ${wd.amount}",
                    color = PrimaryYellow,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.widthIn(min = 80.dp),
                    textAlign = androidx.compose.ui.text.style.TextAlign.End
                )
            }
            if (isRejected && hasRejectionNote) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = wd.admin_note!!,
                    color = TextGrey,
                    fontSize = 13.sp,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}

@Composable
fun TransactionItem(title: String, amount: String, date: String) {
    Surface(
        color = SurfaceColor,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(title, color = TextWhite, fontWeight = FontWeight.Bold)
                Text(date, color = TextGrey, fontSize = 12.sp)
            }
            Spacer(modifier = Modifier.width(16.dp))
            Text(
                text = "₹ $amount",
                color = PrimaryYellow,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.widthIn(min = 80.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.End
            )
        }
    }
}

@Composable
fun BettingItem(roundId: String, number: String, amount: String, status: String, statusColor: Color, date: String) {
    val context = LocalContext.current
    val diceIconId = context.resources.getIdentifier("ic_gundu_ata_nav", "drawable", context.packageName)
    
    Surface(
        color = SurfaceColor,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (diceIconId != 0) {
                        Image(
                            painter = painterResource(id = diceIconId),
                            contentDescription = null,
                            modifier = Modifier.size(24.dp),
                            contentScale = ContentScale.Fit
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                    }
                    Column {
                        Text(stringResource(R.string.round_id, roundId), color = TextWhite, fontWeight = FontWeight.Bold)
                        Text(stringResource(R.string.bet_on_number_value, number), color = PrimaryYellow, fontSize = 14.sp)
                        Text(date, color = TextGrey, fontSize = 12.sp)
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("₹ $amount", color = TextWhite, fontWeight = FontWeight.Bold)
                    Text(status, color = statusColor, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
fun HistoryTab(text: String, isSelected: Boolean, onClick: () -> Unit) {
    Column(
        modifier = Modifier.clickable { onClick() },
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = text,
            color = if (isSelected) PrimaryYellow else TextGrey,
            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        if (isSelected) {
            Box(
                modifier = Modifier
                    .width(40.dp)
                    .height(3.dp)
                    .clip(RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp))
                    .background(
                        Brush.verticalGradient(listOf(PrimaryYellow, Color.Transparent))
                    )
            )
        }
    }
}

