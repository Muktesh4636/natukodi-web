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
                    "Game Guidelines",
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
                        "How to Play Gundu Ata",
                        color = TextWhite,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold
                    )
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    Text(
                        "Learn the rules and strategies to win big!",
                        color = TextGrey,
                        fontSize = 14.sp
                    )
                }
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Game Rules Section
            GuidelineSection(
                title = "Game Rules",
                icon = Icons.Filled.Rule
            ) {
                GuidelineItem(
                    number = "1",
                    title = "Dice Game Basics",
                    description = "Gundu Ata is a dice game where 6 dice are rolled. You bet on numbers 1-6 that you think will appear."
                )
                
                GuidelineItem(
                    number = "2",
                    title = "Winning Conditions",
                    description = "Any number appearing 2 or more times is a winner. The payout multiplier equals the frequency (e.g., if a number appears 3 times, multiplier is 3x)."
                )
                
                GuidelineItem(
                    number = "3",
                    title = "Payout Calculation",
                    description = "If you bet ₹100 on a number that appears 3 times, you win ₹300 (100 × 3). Players receive 100% of the payout with no commission."
                )
                
                GuidelineItem(
                    number = "4",
                    title = "No Winners",
                    description = "If no number appears 2+ times in a round, there are no winners and all bets are lost."
                )
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Betting Strategy Section
            GuidelineSection(
                title = "Betting Strategy",
                icon = Icons.Filled.TrendingUp
            ) {
                GuidelineItem(
                    number = "1",
                    title = "Start Small",
                    description = "Begin with smaller bets to understand the game patterns and build your confidence."
                )
                
                GuidelineItem(
                    number = "2",
                    title = "Diversify Your Bets",
                    description = "Consider betting on multiple numbers to increase your chances of winning, but manage your bankroll wisely."
                )
                
                GuidelineItem(
                    number = "3",
                    title = "Watch the Patterns",
                    description = "Observe previous rounds to identify patterns, though each round is independent and random."
                )
                
                GuidelineItem(
                    number = "4",
                    title = "Set Limits",
                    description = "Always set a budget and stick to it. Never bet more than you can afford to lose."
                )
            }
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Tips Section
            GuidelineSection(
                title = "Pro Tips",
                icon = Icons.Filled.Lightbulb
            ) {
                GuidelineItem(
                    number = "•",
                    title = "Timing Matters",
                    description = "Place your bets before the round closes. Late bets may not be accepted."
                )
                
                GuidelineItem(
                    number = "•",
                    title = "Check Your Balance",
                    description = "Always ensure you have sufficient balance before placing bets."
                )
                
                GuidelineItem(
                    number = "•",
                    title = "Review History",
                    description = "Check your betting history to track your performance and learn from past rounds."
                )
                
                GuidelineItem(
                    number = "•",
                    title = "Stay Updated",
                    description = "Keep an eye on announcements and system information for any game updates or special events."
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
                            "Important Notes",
                            color = PrimaryYellow,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold
                        )
                        
                        Spacer(modifier = Modifier.height(8.dp))
                        
                        Text(
                            "• All dice rolls are random and fair\n" +
                            "• Each round is independent\n" +
                            "• Results are final once dice are rolled\n" +
                            "• Play responsibly and within your means\n" +
                            "• Contact support if you have any questions\n\n" +
                            "• Company reserves the right to suspend/void any id/bets if the same is found to be illegitimate. For example incase of VPN/robot-use/multiple entry from same or different IP and others. Note: only winning bets will be voided.\n" +
                            "• In any circumstances management decision will be final.",
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
