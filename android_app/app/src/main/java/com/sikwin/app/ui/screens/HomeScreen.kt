package com.sikwin.app.ui.screens

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import com.sikwin.app.R
import androidx.compose.ui.text.font.FontWeight
import kotlinx.coroutines.delay
import kotlinx.coroutines.yield
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntOffset
import com.sikwin.app.ui.theme.*
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.ui.PlayerView
import android.net.Uri
import android.content.Intent
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import androidx.compose.ui.zIndex
import androidx.compose.ui.text.font.FontFamily
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: GunduAtaViewModel,
    onGameClick: (String) -> Unit,
    onNavigate: (String) -> Unit
) {
    var searchQuery by remember { mutableStateOf("") }
    var showGuestSpinWheel by remember { mutableStateOf(false) }
    var guestWheelCloseCount by remember { mutableIntStateOf(0) }
    var showLoginPopup by remember { mutableStateOf(false) }
    
    if (showLoginPopup) {
        AlertDialog(
            onDismissRequest = { showLoginPopup = false },
            title = { Text("Login Required", fontWeight = FontWeight.Bold) },
            text = { Text("Please sign up to access the Gundu Ata game and start winning!") },
            confirmButton = {
                Button(
                    onClick = {
                        showLoginPopup = false
                        onNavigate("signup")
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow)
                ) {
                    Text("Sign Up", color = BlackBackground, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showLoginPopup = false }) {
                    Text("Cancel", color = TextGrey)
                }
            },
            containerColor = SurfaceColor,
            titleContentColor = TextWhite,
            textContentColor = TextGrey
        )
    }
    
    // Show guest spin wheel after 3 seconds if not logged in
    LaunchedEffect(viewModel.loginSuccess, guestWheelCloseCount) {
        if (!viewModel.loginSuccess && guestWheelCloseCount < 1) {
            delay(3000)
            showGuestSpinWheel = true
        }
    }

    if (showGuestSpinWheel) {
        GuestSpinWheelDialog(
            onDismiss = { 
                showGuestSpinWheel = false
                guestWheelCloseCount++
            },
            onRegisterClick = { amount ->
                showGuestSpinWheel = false
                onNavigate("signup?ref=&spin=$amount")
            }
        )
    }
    
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                viewModel.checkSession()
                if (viewModel.loginSuccess) {
                    viewModel.fetchWallet()
                    viewModel.fetchProfile()
                    // Start pre-loading timer when app is resumed
                    viewModel.startTimerPreloading()
                }
            } else if (event == Lifecycle.Event.ON_PAUSE) {
                // Stop pre-loading when app goes to background to save battery
                viewModel.stopTimerPreloading()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            viewModel.stopTimerPreloading()
        }
    }

    Scaffold(
        topBar = { 
            HomeTopBar(
                viewModel = viewModel,
                balance = viewModel.wallet?.balance ?: "0.00",
                isLoggedIn = viewModel.loginSuccess,
                onWalletClick = { onNavigate("wallet") },
                onDepositClick = { onNavigate("deposit") },
                onNavigate = onNavigate
            ) 
        },
        bottomBar = { HomeBottomNavigation(currentRoute = "home", viewModel = viewModel, onNavigate = onNavigate) },
        containerColor = BlackBackground
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
            ) {
                // Search Bar
                SearchBar(onSearch = { searchQuery = it })
                
                if (searchQuery.isEmpty()) {
                    // Banners
                    PromotionalBanners(viewModel, onNavigate)
                    
                    // Hot Games
                    SectionHeader(title = "Hot games")
                    HotGamesGrid(
                        viewModel = viewModel,
                        onGameClick = { gameId ->
                            if (!viewModel.loginSuccess) {
                                showLoginPopup = true
                            } else {
                                onGameClick(gameId)
                            }
                        },
                        onNavigate = onNavigate,
                        onRequireLogin = { showLoginPopup = true }
                    )
                } else {
                    // Search Results
                    SectionHeader(title = "Search Results")
                    val games = listOf(
                        GameItem("Gundu Ata", "gundu_ata", Color(0xFF1565C0))
                    ).filter { it.name.contains(searchQuery, ignoreCase = true) }
                    
                    if (games.isNotEmpty()) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp),
                            horizontalArrangement = Arrangement.Start
                        ) {
                            games.forEach { game ->
                                GameCard(
                                    game = game,
                                    modifier = Modifier.fillMaxWidth(0.5f),
                                    onGameClick = { gameId ->
                                        if (!viewModel.loginSuccess) {
                                            showLoginPopup = true
                                        } else {
                                            onGameClick(gameId)
                                        }
                                    }
                                )
                            }
                        }
                    } else {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text("No games found for \"$searchQuery\"", color = TextGrey)
                        }
                    }
                }
                
                Spacer(modifier = Modifier.height(20.dp))
            }

        }
    }
}

@Composable
fun HomeTopBar(
    viewModel: GunduAtaViewModel,
    balance: String,
    isLoggedIn: Boolean,
    onWalletClick: () -> Unit,
    onDepositClick: () -> Unit,
    onNavigate: (String) -> Unit
) {
    val context = LocalContext.current
    
    // Shimmering light pass effect
    val shimmerTransition = rememberInfiniteTransition(label = "shimmer")
    val shimmerTranslate by shimmerTransition.animateFloat(
        initialValue = -300f,
        targetValue = 1000f,
        animationSpec = infiniteRepeatable(
            animation = tween(2000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "shimmerTranslate"
    )

    val textShimmerBrush = Brush.linearGradient(
        colors = listOf(
            PrimaryYellow,
            Color.White,
            PrimaryYellow
        ),
        start = androidx.compose.ui.geometry.Offset(shimmerTranslate, shimmerTranslate),
        end = androidx.compose.ui.geometry.Offset(shimmerTranslate + 200f, shimmerTranslate + 200f)
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(BlackBackground)
            .padding(horizontal = 8.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .weight(1f)
                .clickable { onNavigate("gundu_ata") }
        ) {
            Image(
                painter = painterResource(id = R.drawable.app_logo),
                contentDescription = "App Logo",
                modifier = Modifier
                    .size(32.dp)
                    .clip(RoundedCornerShape(8.dp))
            )
            Spacer(modifier = Modifier.width(4.dp))
            
            Text(
                text = "Gundu Ata",
                style = androidx.compose.ui.text.TextStyle(
                    brush = textShimmerBrush,
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Black,
                    fontFamily = FontFamily.Serif,
                    letterSpacing = 0.5.sp
                ),
                maxLines = 1
            )
        }
        
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.wrapContentWidth()
        ) {
            if (isLoggedIn) {
                // Balance Pill
                Surface(
                    color = SurfaceColor,
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(
                            modifier = Modifier.clickable { onDepositClick() },
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("₹", color = PrimaryYellow, fontWeight = FontWeight.Bold)
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(balance, color = TextWhite, fontWeight = FontWeight.Bold)
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Icon(
                            Icons.Default.AddBox,
                            contentDescription = "Add money",
                            tint = PrimaryYellow,
                            modifier = Modifier
                                .size(20.dp)
                                .clickable { onDepositClick() }
                        )
                    }
                }
            } else {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.wrapContentWidth()
                ) {
                    TextButton(
                        onClick = { onNavigate("login") },
                        contentPadding = PaddingValues(horizontal = 8.dp)
                    ) {
                        Text(
                            text = "Login",
                            color = TextWhite,
                            fontWeight = FontWeight.Bold,
                            fontSize = 14.sp
                        )
                    }
                    Spacer(modifier = Modifier.width(4.dp))
                    Button(
                        onClick = { onNavigate("signup") },
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                        shape = RoundedCornerShape(20.dp),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                    ) {
                        Text(
                            text = "Register",
                            color = BlackBackground,
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp,
                            maxLines = 1
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchBar(onSearch: (String) -> Unit) {
    var searchQuery by remember { mutableStateOf("") }
    
    OutlinedTextField(
        value = searchQuery,
        onValueChange = { 
            searchQuery = it
            onSearch(it)
        },
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        placeholder = { Text("Search games...", color = TextGrey) },
        leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = TextWhite) },
        trailingIcon = {
            if (searchQuery.isNotEmpty()) {
                IconButton(onClick = { 
                    searchQuery = ""
                    onSearch("")
                }) {
                    Icon(Icons.Default.Close, contentDescription = "Clear", tint = TextGrey)
                }
            }
        },
        colors = TextFieldDefaults.outlinedTextFieldColors(
            containerColor = SurfaceColor,
            unfocusedBorderColor = Color.Transparent,
            focusedBorderColor = PrimaryYellow,
            focusedTextColor = TextWhite,
            unfocusedTextColor = TextWhite
        ),
        shape = RoundedCornerShape(12.dp),
        singleLine = true
    )
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PromotionalBanners(
    viewModel: GunduAtaViewModel,
    onNavigate: (String) -> Unit
) {
    val pageCount = 4
    val virtualCount = 1000 * pageCount
    val pagerState = rememberPagerState(
        initialPage = virtualCount / 2,
        pageCount = { virtualCount }
    )

    var lastClickTime by remember { mutableStateOf(0L) }
    val clickCooldown = 1000L

    fun handleBannerClick(route: String) {
        if (!viewModel.loginSuccess) {
            onNavigate("login")
            return
        }
        val currentTime = System.currentTimeMillis()
        if (currentTime - lastClickTime > clickCooldown) {
            lastClickTime = currentTime
            onNavigate(route)
        }
    }

    LaunchedEffect(Unit) {
        while (true) {
            yield()
            delay(4000)
            pagerState.animateScrollToPage(pagerState.currentPage + 1)
        }
    }

    Column {
        HorizontalPager(
            state = pagerState,
            modifier = Modifier
                .fillMaxWidth()
                .height(180.dp)
                .padding(horizontal = 16.dp),
            pageSpacing = 16.dp
        ) { virtualPage ->
            val page = virtualPage % pageCount
            val banner = when(page) {
                0 -> BannerData("REFER & EARN", "Invite friends and earn up to ₹1000 bonus!", "INVITE", listOf(Color(0xFF455A64), Color(0xFF263238)), { handleBannerClick("affiliate") })
                1 -> BannerData("MEGA SPIN", "Deposit ₹2000 or more to spin the wheel!", "SPIN NOW", listOf(Color(0xFF4A148C), Color(0xFF880E4F)), { handleBannerClick("lucky_draw") })
                2 -> BannerData("DAILY REWARD", "SPIN THE WHEEL FOR BONUS!", "SPIN NOW", listOf(Color(0xFFF9A825), Color(0xFFF57F17)), { handleBannerClick("lucky_wheel") })
                else -> BannerData("USDT SPECIAL ₮", "Get 5% EXTRA CASHBACK on all USDT deposits!", "DEPOSIT NOW", listOf(Color(0xFF00897B), Color(0xFF004D40)), { handleBannerClick("deposit?method=USDT") })
            }

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .clip(RoundedCornerShape(16.dp))
                    .background(Brush.horizontalGradient(banner.gradient)),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(16.dp)) {
                    Text(banner.title, color = PrimaryYellow, fontWeight = FontWeight.ExtraBold, fontSize = 24.sp)
                    Text(banner.subtitle, color = TextWhite, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = banner.onClick,
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                        shape = RoundedCornerShape(20.dp)
                    ) {
                        Text(banner.buttonText, color = BlackBackground, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
        
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp),
            horizontalArrangement = Arrangement.Center
        ) {
            repeat(pageCount) { iteration ->
                val color = if (pagerState.currentPage % pageCount == iteration) PrimaryYellow else TextGrey
                Box(
                    modifier = Modifier
                        .padding(2.dp)
                        .clip(CircleShape)
                        .background(color)
                        .size(8.dp)
                )
            }
        }
    }
}

data class BannerData(
    val title: String,
    val subtitle: String,
    val buttonText: String,
    val gradient: List<Color>,
    val onClick: () -> Unit
)

@Composable
fun SectionHeader(title: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(title, color = TextWhite, fontSize = 20.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun HotGamesGrid(
    viewModel: GunduAtaViewModel,
    onGameClick: (String) -> Unit,
    onNavigate: (String) -> Unit,
    onRequireLogin: () -> Unit
) {
    val games = listOf(GameItem("Gundu Ata", "gundu_ata", Color(0xFF1565C0)))
    val context = LocalContext.current
    
    // List of fake winning names and amounts
    val baseWinnings = remember {
        listOf(
            "Muktesh", "Sai Krishna", "Mahesh", "Rahul", "Priya", "Vikram", "Anjali", "Suresh", "Kiran", "Deepak",
            "Amit", "Sneha", "Rohan", "Neha", "Arjun", "Pooja", "Karan", "Ishita", "Sanjay", "Ritu",
            "Vijay", "Anita", "Rajesh", "Sunita", "Manoj", "Kavita", "Vinay", "Meena", "Sandeep", "Rekha",
            "Abhishek", "Swati", "Prashant", "Aarti", "Alok", "Shweta", "Vivek", "Jyoti", "Ashish", "Priyanka",
            "Manish", "Rani", "Dinesh", "Sonia", "Harish", "Preeti", "Naveen", "Madhu", "Pankaj", "Seema",
            "Rakesh", "Anu", "Om", "Lata", "Ram", "Gita", "Shyam", "Radha", "Krishna", "Meera",
            "Bala", "Lakshmi", "Murugan", "Parvati", "Ganesh", "Saraswati", "Kartik", "Durga", "Shiva", "Kali",
            "Mohan", "Indira", "Jawahar", "Sarojini", "Subhash", "Aruna", "Bhagat", "Kamala", "Sardar", "Kasturba",
            "Vikram", "Kalpana", "Homi", "Shakuntala", "C.V. Raman", "Janaki", "Visvesvaraya", "Asima", "Srinivasa", "Tessy",
            "Sachin", "Mithali", "Virat", "Mary Kom", "Dhoni", "Saina", "Kapil", "Sindhu", "Sunil", "Dipa",
            "Aamir", "Deepika", "Shah Rukh", "Alia", "Salman", "Priyanka", "Akshay", "Kareena", "Hrithik", "Katrina",
            "Ranbir", "Anushka", "Ranveer", "Sonam", "Varun", "Shraddha", "Siddharth", "Jacqueline", "Tiger", "Disha",
            "Ayushmann", "Taapsee", "Rajkummar", "Bhumi", "Vicky", "Kriti", "Kartik", "Kiara", "Ishaan", "Sara",
            "Aditya", "Janhvi", "Ananya", "Tara", "Ishaan", "Rakul", "Vijay", "Rashmika", "Dulquer", "Sai Pallavi",
            "Prabhas", "Samantha", "Mahesh Babu", "Nayanthara", "Allu Arjun", "Keerthy", "Ram Charan", "Trisha", "NTR Jr", "Tamannaah",
            "Yash", "Pooja Hegde", "Sudeep", "Anupama", "Darshan", "Rashmika", "Puneeth", "Srinidhi", "Rishab", "Sapthami",
            "Fahadh", "Nazriya", "Prithviraj", "Parvathy", "Nivin", "Manju", "Tovino", "Keerthy", "Dulquer", "Aishwarya",
            "Suriya", "Jyothika", "Karthi", "Nayanthara", "Dhanush", "Sai Pallavi", "Vijay Sethupathi", "Keerthy", "Sivakarthikeyan", "Trisha",
            "Mammootty", "Shobana", "Mohanlal", "Revathi", "Jayaram", "Urvashi", "Suresh Gopi", "Geetha", "Dileep", "Kavya",
            "Amir", "Zahra", "Omar", "Fatima", "Ali", "Maryam", "Hassan", "Aisha", "Hussein", "Khadija",
            "John", "Mary", "David", "Sarah", "Michael", "Elizabeth", "James", "Jennifer", "Robert", "Linda",
            "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Margaret", "Charles", "Karen",
            "Christopher", "Nancy", "Daniel", "Lisa", "Matthew", "Betty", "Anthony", "Dorothy", "Mark", "Sandra",
            "Donald", "Ashley", "Steven", "Kimberly", "Paul", "Donna", "Andrew", "Emily", "Joshua", "Michelle",
            "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Melissa", "George", "Deborah", "Timothy", "Stephanie",
            "Ronald", "Rebecca", "Edward", "Laura", "Jason", "Sharon", "Jeffrey", "Cynthia", "Ryan", "Kathleen",
            "Jacob", "Amy", "Gary", "Shirley", "Nicholas", "Angela", "Eric", "Helen", "Jonathan", "Anna",
            "Stephen", "Brenda", "Larry", "Pamela", "Justin", "Nicole", "Scott", "Emma", "Brandon", "Samantha",
            "Benjamin", "Katherine", "Samuel", "Christine", "Gregory", "Debra", "Alexander", "Rachel", "Frank", "Catherine",
            "Patrick", "Carolyn", "Raymond", "Janet", "Jack", "Ruth", "Dennis", "Maria", "Jerry", "Heather",
            "Tyler", "Diane", "Aaron", "Virginia", "Jose", "Julie", "Adam", "Joyce", "Nathan", "Victoria",
            "Henry", "Olivia", "Douglas", "Kelly", "Zachary", "Christina", "Peter", "Lauren", "Kyle", "Joan",
            "Ethan", "Evelyn", "Walter", "Judith", "Noah", "Megan", "Jeremy", "Cheryl", "Christian", "Andrea",
            "Keith", "Hannah", "Roger", "Martha", "Terry", "Jacqueline", "Gerald", "Frances", "Harold", "Gloria",
            "Sean", "Ann", "Austin", "Teresa", "Carl", "Kathryn", "Arthur", "Sara", "Lawrence", "Janice",
            "Dylan", "Jean", "Jesse", "Alice", "Jordan", "Madison", "Bryan", "Doris", "Billy", "Abigail",
            "Joe", "Julia", "Bruce", "Judy", "Gabriel", "Grace", "Logan", "Denise", "Albert", "Amber",
            "Willie", "Marilyn", "Alan", "Beverly", "Juan", "Danielle", "Wayne", "Theresa", "Elijah", "Sophia",
            "Randy", "Marie", "Roy", "Diana", "Vincent", "Brittany", "Ralph", "Natalie", "Eugene", "Isabella",
            "Russell", "Charlotte", "Bobby", "Rose", "Mason", "Alexis", "Philip", "Kayla", "Louis", "Alice",
            "Aarav", "Aanya", "Vivaan", "Diya", "Aditya", "Pari", "Vihaan", "Ananya", "Arjun", "Saanvi",
            "Sai", "Ira", "Reyansh", "Avni", "Krishna", "Prisha", "Ishaan", "Riya", "Shaurya", "Aadhya",
            "Aryan", "Myra", "Ayush", "Anika", "Atharv", "Navya", "Ganesh", "Kavya", "Advait", "Ishani",
            "Kabir", "Zoya", "Tushar", "Kiara", "Naksh", "Sara", "Arnav", "Vanya", "Rudr", "Shanaya",
            "Shivansh", "Kyra", "Kian", "Siya", "Veer", "Inaya", "Aaryan", "Aavya", "Rudra", "Amaira",
            "Vedant", "Mishka", "Kush", "Anvi", "Yash", "Aarna", "Dev", "Sana", "Rohan", "Zara",
            "Aadi", "Hazel", "Dhruv", "Aayat", "Kabir", "Meher", "Viaan", "Amaya", "Darsh", "Kaira",
            "Ranbir", "Miraya", "Agastya", "Riddhima", "Abeer", "Anaya", "Yuvan", "Shanaya", "Ishaan", "Zoya"
        )
    }
    
    val winnings = remember(baseWinnings, viewModel.userProfile, viewModel.bettingHistory) {
        val list = baseWinnings.map { "$it +${(100..5000).random()}" }.toMutableList()
        
        // Add current user if they have placed a bet
        val currentUser = viewModel.userProfile?.username
        if (currentUser != null && viewModel.bettingHistory.isNotEmpty()) {
            list.add(0, "$currentUser +${(100..2000).random()}")
        }
        list
    }
    
    // State to track active winning particles
    val activeWinnings = remember { mutableStateListOf<WinningParticle>() }
    var nextId by remember { mutableIntStateOf(0) }
    
    // Detect resume from recent tabs - add 2s delay before sending names to fix glitch
    val lifecycleOwner = LocalLifecycleOwner.current
    var hasBeenPaused by remember { mutableStateOf(false) }
    var resumeTrigger by remember { mutableIntStateOf(0) }
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_PAUSE -> hasBeenPaused = true
                Lifecycle.Event.ON_RESUME -> {
                    if (hasBeenPaused) {
                        resumeTrigger++
                    }
                }
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    
    LaunchedEffect(resumeTrigger) {
        activeWinnings.clear()
        // 2 second delay when resuming from recent tabs to prevent glitch
        if (resumeTrigger > 0) {
            delay(2000)
        }
        while (true) {
            val name = if (winnings.isNotEmpty()) winnings.random() else "Player +100"
            activeWinnings.add(WinningParticle(id = nextId++, text = name))
            delay(1200) // Spawn a new name every 1.2 seconds for continuous flow
        }
    }
    
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp)
    ) {
        // Game Card centered
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center
        ) {
            games.forEach { game ->
                GameCard(game, Modifier.fillMaxWidth(0.5f), onGameClick)
            }
        }

        // Customer Support Icon - opposite side of treasury box (left), dropdown shows only WhatsApp & Telegram
        var supportMenuExpanded by remember { mutableStateOf(false) }
        // Auto-open on home page load, show for 3 seconds, then close
        LaunchedEffect(Unit) {
            supportMenuExpanded = true
            delay(3000)
            supportMenuExpanded = false
        }
        Box(
            modifier = Modifier
                .align(Alignment.CenterStart)
                .offset(y = 28.dp, x = 4.dp),
            contentAlignment = Alignment.BottomCenter
        ) {
            if (!supportMenuExpanded) {
                IconButton(
                    onClick = { supportMenuExpanded = true },
                    modifier = Modifier
                        .size(48.dp)
                        .background(Color.Black.copy(alpha = 0.5f), CircleShape)
                ) {
                    Icon(
                        imageVector = Icons.Default.SupportAgent,
                        contentDescription = "Customer Support",
                        tint = PrimaryYellow,
                        modifier = Modifier.size(28.dp)
                    )
                }
            }
            if (supportMenuExpanded) {
                val density = LocalDensity.current
                val scaleAlpha = remember { Animatable(0f) }
                LaunchedEffect(Unit) {
                    scaleAlpha.animateTo(
                        targetValue = 1f,
                        animationSpec = tween(durationMillis = 250, easing = FastOutSlowInEasing)
                    )
                }
                Popup(
                    alignment = Alignment.TopStart,
                    offset = IntOffset(0, with(density) { (-100).dp.roundToPx() }),
                    onDismissRequest = { supportMenuExpanded = false },
                    properties = PopupProperties(
                        focusable = true,
                        dismissOnBackPress = true,
                        dismissOnClickOutside = true
                    )
                ) {
                    Column(
                        modifier = Modifier
                            .graphicsLayer(
                                scaleX = scaleAlpha.value,
                                scaleY = scaleAlpha.value,
                                alpha = scaleAlpha.value,
                                transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0.5f, 1f)
                            )
                            .background(BlackBackground)
                            .padding(8.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        IconButton(
                            onClick = {
                                supportMenuExpanded = false
                                try {
                                    val intent = Intent(Intent.ACTION_VIEW)
                                    intent.data = Uri.parse("https://wa.me/919999999999")
                                    context.startActivity(intent)
                                } catch (e: Exception) {}
                            },
                            modifier = Modifier.size(52.dp)
                        ) {
                            Icon(
                                painter = painterResource(id = R.drawable.ic_whatsapp),
                                contentDescription = "WhatsApp",
                                modifier = Modifier.size(40.dp),
                                tint = Color(0xFF25D366)
                            )
                        }
                        IconButton(
                            onClick = {
                                supportMenuExpanded = false
                                try {
                                    val intent = Intent(Intent.ACTION_VIEW)
                                    intent.data = Uri.parse("https://t.me/your_telegram_handle")
                                    context.startActivity(intent)
                                } catch (e: Exception) {}
                            },
                            modifier = Modifier.size(52.dp)
                        ) {
                            Icon(
                                painter = painterResource(id = R.drawable.ic_telegram),
                                contentDescription = "Telegram",
                                modifier = Modifier.size(40.dp),
                                tint = Color(0xFF0088cc)
                            )
                        }
                    }
                }
            }
        }

                // Treasury Box Icon and Continuous Winnings Animation
                val treasuryBoxId = context.resources.getIdentifier("ic_treasury_box", "drawable", context.packageName)
                if (treasuryBoxId != 0) {
                    // Real-box shake animation logic
                    val infiniteTransition = rememberInfiniteTransition(label = "shake")
                    
                    // Rotation for side-to-side wobble
                    val shakeRotation by infiniteTransition.animateFloat(
                        initialValue = 0f,
                        targetValue = 0f,
                        animationSpec = infiniteRepeatable(
                            animation = keyframes {
                                durationMillis = 6000 // Total cycle: 6 seconds
                                0f at 0
                                0f at 5500 // Wait for 5.5 seconds
                                -8f at 5600 // Start shaking
                                8f at 5700
                                -6f at 5800
                                6f at 5900
                                0f at 6000 // End shake
                            },
                            repeatMode = RepeatMode.Restart
                        ),
                        label = "shakeRotation"
                    )

                    // Scale for a "jumpy" effect
                    val shakeScale by infiniteTransition.animateFloat(
                        initialValue = 1f,
                        targetValue = 1f,
                        animationSpec = infiniteRepeatable(
                            animation = keyframes {
                                durationMillis = 6000 // Total cycle: 6 seconds
                                1f at 0
                                1f at 5500
                                1.15f at 5650
                                1f at 5800
                                1.1f at 5900
                                1f at 6000
                            },
                            repeatMode = RepeatMode.Restart
                        ),
                        label = "shakeScale"
                    )

                    Box(
                        modifier = Modifier
                            .align(Alignment.CenterEnd)
                            .offset(y = 10.dp, x = 45.dp),
                        contentAlignment = Alignment.BottomCenter
                    ) {
                        // Treasury Box Image (SHAKING) - Layered behind names initially
                        Box(
                            modifier = Modifier
                                .zIndex(1f) // Ensure box is below names that have come out
                                .graphicsLayer(
                                    rotationZ = shakeRotation,
                                    scaleX = shakeScale,
                                    scaleY = shakeScale,
                                    transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0.5f, 1f)
                                )
                        ) {
                            Image(
                                painter = painterResource(id = treasuryBoxId),
                                contentDescription = "Treasury Box",
                                modifier = Modifier
                                    .size(64.dp)
                                    .clickable {
                                        if (viewModel.loginSuccess) {
                                            onNavigate("leaderboard")
                                        } else {
                                            onRequireLogin()
                                        }
                                    },
                                contentScale = ContentScale.Fit
                            )
                        }

                        // Continuous Winnings Particles container (STABLE - No shake)
                        // Positioned so names start inside/behind the box
                        Box(
                            modifier = Modifier
                                .width(150.dp)
                                .height(200.dp)
                                .zIndex(2f), // Names appear on top of the box
                            contentAlignment = Alignment.BottomCenter
                        ) {
                            activeWinnings.forEach { particle ->
                                key(particle.id) {
                                    WinningTextParticle(
                                        text = particle.text,
                                        onAnimationFinished = { activeWinnings.remove(particle) }
                                    )
                                }
                            }
                        }
                    }
                }
    }
}

data class WinningParticle(val id: Int, val text: String)

@Composable
fun WinningTextParticle(text: String, onAnimationFinished: () -> Unit) {
    // Animation state for vertical movement and alpha
    val animProgress = remember { androidx.compose.animation.core.Animatable(0f) }
    
    LaunchedEffect(Unit) {
        animProgress.animateTo(
            targetValue = 1f,
            animationSpec = tween(durationMillis = 3000, easing = LinearEasing)
        )
        onAnimationFinished()
    }
    
    // Calculate offset and alpha based on progress
    // Start from y=0 (inside box) and move up to -150dp
    val yOffset = - (animProgress.value * 150).dp 
    
    // Fade in quickly at start, then stay visible, then fade out at end
    val alpha = when {
        animProgress.value < 0.1f -> animProgress.value / 0.1f // Faster fade in
        animProgress.value > 0.7f -> 1f - (animProgress.value - 0.7f) / 0.3f // Fade out
        else -> 1f
    }
    
    // Scale up slightly as it "pops" out of the box
    val scale = if (animProgress.value < 0.2f) {
        0.5f + (animProgress.value / 0.2f) * 0.5f
    } else 1f
    
    Text(
        text = text,
        color = PrimaryYellow,
        fontSize = 12.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .offset(y = yOffset)
            .graphicsLayer(
                alpha = alpha,
                scaleX = scale,
                scaleY = scale
            )
    )
}

data class GameItem(val name: String, val id: String, val color: Color)

@Composable
fun GameCard(game: GameItem, modifier: Modifier, onGameClick: (String) -> Unit) {
    val context = LocalContext.current
    Box(
        modifier = modifier.clickable { onGameClick(game.id) },
        contentAlignment = Alignment.BottomCenter
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Box(
                modifier = Modifier
                    .aspectRatio(0.7f)
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(game.color),
                contentAlignment = Alignment.BottomCenter
            ) {
                if (game.id == "gundu_ata") {
                    VideoPlayer(videoResId = R.raw.gundu_ata_video, modifier = Modifier.fillMaxSize())
                } else {
                    Image(
                        painter = painterResource(id = R.drawable.gundu_ata_bg),
                        contentDescription = null,
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Crop
                    )
                    Text(
                        game.name,
                        color = TextWhite,
                        fontWeight = FontWeight.Bold,
                        fontSize = 18.sp,
                        modifier = Modifier.padding(bottom = 20.dp)
                    )
                }
            }
            Spacer(modifier = Modifier.height(8.dp))
            Text(game.name, color = TextGrey, fontSize = 14.sp)
        }
    }
}

@Composable
fun VideoPlayer(videoResId: Int, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().apply {
            val uri = Uri.parse("android.resource://${context.packageName}/$videoResId")
            setMediaItem(MediaItem.fromUri(uri))
            repeatMode = Player.REPEAT_MODE_ALL
            playWhenReady = false
            prepare()
        }
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> exoPlayer.playWhenReady = true
                Lifecycle.Event.ON_PAUSE -> exoPlayer.playWhenReady = false
                Lifecycle.Event.ON_DESTROY -> exoPlayer.release()
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            exoPlayer.release()
        }
    }

    AndroidView(
        factory = { ctx ->
            PlayerView(ctx).apply {
                player = exoPlayer
                useController = false
                resizeMode = androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM
            }
        },
        modifier = modifier
    )
}

@Composable
fun HomeBottomNavigation(currentRoute: String, viewModel: GunduAtaViewModel, onNavigate: (String) -> Unit) {
    var showLoginPopup by remember { mutableStateOf(false) }
    var lastGameLaunchTime by remember { mutableStateOf(0L) }
    val gameLaunchCooldown = 1500L // Prevent double-tap crash

    if (showLoginPopup) {
        AlertDialog(
            onDismissRequest = { showLoginPopup = false },
            title = { Text("Login Required", fontWeight = FontWeight.Bold) },
            text = { Text("Please sign up to access the Gundu Ata game and start winning!") },
            confirmButton = {
                Button(
                    onClick = {
                        showLoginPopup = false
                        onNavigate("signup")
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow)
                ) {
                    Text("Sign Up", color = BlackBackground, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showLoginPopup = false }) {
                    Text("Cancel", color = TextGrey)
                }
            },
            containerColor = SurfaceColor,
            titleContentColor = TextWhite,
            textContentColor = TextGrey
        )
    }

    NavigationBar(
        containerColor = BottomNavBackground,
        tonalElevation = 8.dp
    ) {
        val items = listOf(
            BottomNavItem("Home", "home", Icons.Default.Home),
            BottomNavItem("Gundu Ata", "gundu_ata", Icons.Default.Casino),
            BottomNavItem("Me", "me", Icons.Default.AccountCircle)
        )
        
        items.forEach { item ->
            NavigationBarItem(
                selected = currentRoute == item.route,
                onClick = { 
                    if (currentRoute != item.route) {
                        if (item.route == "gundu_ata") {
                            if (!viewModel.loginSuccess) {
                                showLoginPopup = true
                            } else {
                                val now = System.currentTimeMillis()
                                if (now - lastGameLaunchTime >= gameLaunchCooldown) {
                                    lastGameLaunchTime = now
                                    viewModel.syncAuthToUnity()
                                    onNavigate(item.route)
                                }
                            }
                        } else {
                            onNavigate(item.route)
                        }
                    }
                },
                icon = { 
                    if (item.route == "gundu_ata") {
                        val context = LocalContext.current
                        val diceIconId = context.resources.getIdentifier("ic_gundu_ata_nav", "drawable", context.packageName)
                        if (diceIconId != 0) {
                            Image(
                                painter = painterResource(id = diceIconId),
                                contentDescription = null,
                                modifier = Modifier.size(24.dp),
                                contentScale = ContentScale.Fit,
                                colorFilter = if (currentRoute == item.route) null else androidx.compose.ui.graphics.ColorFilter.tint(TextGrey)
                            )
                        } else {
                            Icon(item.icon, contentDescription = null)
                        }
                    } else {
                        Icon(item.icon, contentDescription = null)
                    }
                },
                label = { Text(item.name) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = PrimaryYellow,
                    selectedTextColor = PrimaryYellow,
                    unselectedIconColor = TextGrey,
                    unselectedTextColor = TextGrey,
                    indicatorColor = Color.Transparent
                )
            )
        }
    }
}

@Composable
fun WhatsAppSupportButton() {
    val context = LocalContext.current
    val phoneNumber = "919999999999" // Replace with actual support number
    
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .clickable {
                try {
                    val intent = Intent(Intent.ACTION_VIEW)
                    intent.data = Uri.parse("https://wa.me/$phoneNumber")
                    context.startActivity(intent)
                } catch (e: Exception) {
                    // Fallback if WhatsApp is not installed
                }
            },
        color = Color(0xFF25D366), // WhatsApp Green
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center
        ) {
            Icon(
                painter = painterResource(id = R.drawable.ic_whatsapp),
                contentDescription = "WhatsApp",
                tint = Color.White,
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                "Contact Support on WhatsApp",
                color = Color.White,
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )
        }
    }
}

data class BottomNavItem(val name: String, val route: String, val icon: ImageVector)
