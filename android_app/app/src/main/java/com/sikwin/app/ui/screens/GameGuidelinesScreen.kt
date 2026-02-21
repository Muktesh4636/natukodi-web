package com.sikwin.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.stringResource
import com.sikwin.app.R
import com.sikwin.app.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GameGuidelinesScreen(
    onBack: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BlackBackground)
    ) {
        TopAppBar(
            title = {
                Text(
                    stringResource(R.string.game_guidelines_title),
                    color = TextWhite,
                    fontWeight = FontWeight.Bold,
                    fontSize = 20.sp
                )
            },
            navigationIcon = {
                IconButton(onClick = onBack) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "Back",
                        tint = TextWhite
                    )
                }
            },
            colors = androidx.compose.material3.TopAppBarDefaults.topAppBarColors(
                containerColor = BlackBackground
            )
        )
        
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp)
        ) {
            // Hero Section
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                color = SurfaceColor
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Surface(
                        modifier = Modifier.size(80.dp),
                        shape = RoundedCornerShape(16.dp),
                        color = PrimaryYellow.copy(alpha = 0.2f)
                    ) {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Filled.Casino,
                                contentDescription = null,
                                tint = PrimaryYellow,
                                modifier = Modifier.size(40.dp)
                            )
                        }
                    }
                    
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    Text(
                        stringResource(R.string.how_to_play),
                        color = TextWhite,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold
                    )
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    Text(
                        stringResource(R.string.learn_rules),
                        color = TextGrey,
                        fontSize = 14.sp
                    )
                }
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Game Rules Section
            GuidelineSection(
                title = stringResource(R.string.game_rules),
                icon = Icons.Filled.Rule
            ) {
                GuidelineItem(
                    number = "1",
                    title = stringResource(R.string.dice_game_basics),
                    description = stringResource(R.string.dice_game_basics_desc)
                )
                
                GuidelineItem(
                    number = "2",
                    title = stringResource(R.string.winning_conditions),
                    description = stringResource(R.string.winning_conditions_desc)
                )
                
                GuidelineItem(
                    number = "3",
                    title = stringResource(R.string.payout_calculation),
                    description = stringResource(R.string.payout_calculation_desc)
                )
                
                GuidelineItem(
                    number = "4",
                    title = stringResource(R.string.no_winners),
                    description = stringResource(R.string.no_winners_desc)
                )
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Betting Strategy Section
            GuidelineSection(
                title = stringResource(R.string.betting_strategy),
                icon = Icons.Filled.TrendingUp
            ) {
                GuidelineItem(
                    number = "1",
                    title = stringResource(R.string.start_small),
                    description = stringResource(R.string.start_small_desc)
                )
                
                GuidelineItem(
                    number = "2",
                    title = stringResource(R.string.diversify_bets),
                    description = stringResource(R.string.diversify_bets_desc)
                )
                
                GuidelineItem(
                    number = "3",
                    title = stringResource(R.string.watch_patterns),
                    description = stringResource(R.string.watch_patterns_desc)
                )
                
                GuidelineItem(
                    number = "4",
                    title = stringResource(R.string.set_limits),
                    description = stringResource(R.string.set_limits_desc)
                )
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Tips Section
            GuidelineSection(
                title = stringResource(R.string.pro_tips),
                icon = Icons.Filled.Lightbulb
            ) {
                GuidelineItem(
                    number = "•",
                    title = stringResource(R.string.timing_matters),
                    description = stringResource(R.string.timing_matters_desc)
                )
                
                GuidelineItem(
                    number = "•",
                    title = stringResource(R.string.check_balance),
                    description = stringResource(R.string.check_balance_desc)
                )
                
                GuidelineItem(
                    number = "•",
                    title = stringResource(R.string.review_history),
                    description = stringResource(R.string.review_history_desc)
                )
                
                GuidelineItem(
                    number = "•",
                    title = stringResource(R.string.stay_updated),
                    description = stringResource(R.string.stay_updated_desc)
                )
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Important Notes Section
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                color = PrimaryYellow.copy(alpha = 0.1f)
            ) {
                Row(
                    modifier = Modifier.padding(20.dp),
                    verticalAlignment = Alignment.Top
                ) {
                    Icon(
                        imageVector = Icons.Filled.Info,
                        contentDescription = null,
                        tint = PrimaryYellow,
                        modifier = Modifier.size(24.dp)
                    )
                    
                    Spacer(modifier = Modifier.width(12.dp))
                    
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            stringResource(R.string.important_notes),
                            color = PrimaryYellow,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold
                        )
                        
                        Spacer(modifier = Modifier.height(8.dp))
                        
                        Text(
                            stringResource(R.string.important_notes_content),
                            color = TextWhite,
                            fontSize = 14.sp,
                            lineHeight = 22.sp
                        )
                    }
                }
            }
            
            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
fun GuidelineSection(
    title: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    content: @Composable ColumnScope.() -> Unit
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = PrimaryYellow,
                modifier = Modifier.size(24.dp)
            )
            
            Spacer(modifier = Modifier.width(12.dp))
            
            Text(
                title,
                color = TextWhite,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold
            )
        }
        
        Spacer(modifier = Modifier.height(16.dp))
        
        content()
    }
}

@Composable
fun GuidelineItem(
    number: String,
    title: String,
    description: String
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        shape = RoundedCornerShape(12.dp),
        color = SurfaceColor
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.Top
        ) {
            // Number Badge
            Surface(
                modifier = Modifier.size(32.dp),
                shape = RoundedCornerShape(8.dp),
                color = PrimaryYellow.copy(alpha = 0.2f)
            ) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        number,
                        color = PrimaryYellow,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            Spacer(modifier = Modifier.width(16.dp))
            
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    title,
                    color = TextWhite,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold
                )
                
                Spacer(modifier = Modifier.height(4.dp))
                
                Text(
                    description,
                    color = TextGrey,
                    fontSize = 14.sp,
                    lineHeight = 20.sp
                )
            }
        }
    }
}
