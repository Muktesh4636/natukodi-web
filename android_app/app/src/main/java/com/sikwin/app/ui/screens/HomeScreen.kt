package com.sikwin.app.ui.screens

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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import com.sikwin.app.R
import androidx.compose.ui.text.font.FontWeight
import kotlinx.coroutines.delay
import kotlinx.coroutines.yield
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import com.sikwin.app.ui.theme.*
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.ui.PlayerView
import android.net.Uri
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.platform.LocalLifecycleOwner
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: GunduAtaViewModel,
    onGameClick: (String) -> Unit,
    onNavigate: (String) -> Unit
) {
    var searchQuery by remember { mutableStateOf("") }
    
    // Pass onNavigate to PromotionalBanners
    PromotionalBanners(onNavigate)
    LaunchedEffect(Unit) {
        if (viewModel.loginSuccess) {
            viewModel.fetchWallet()
        }
    }

    Scaffold(
        topBar = { 
            HomeTopBar(
                balance = viewModel.wallet?.balance ?: "0.00",
                isLoggedIn = viewModel.loginSuccess,
                onWalletClick = { onNavigate("wallet") },
                onNavigate = onNavigate
            ) 
        },
        bottomBar = { HomeBottomNavigation(currentRoute = "home", onNavigate = onNavigate) },
        containerColor = BlackBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
        ) {
            // Search Bar
            SearchBar(onSearch = { searchQuery = it })
            
            if (searchQuery.isEmpty()) {
                // Banners
                PromotionalBanners(onNavigate)
                
                // Hot Games
                SectionHeader(title = "Hot games")
                HotGamesGrid(onGameClick)
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
                            GameCard(game, Modifier.fillMaxWidth(0.5f), onGameClick)
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

@Composable
fun HomeTopBar(
    balance: String, 
    isLoggedIn: Boolean,
    onWalletClick: () -> Unit,
    onNavigate: (String) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(BlackBackground)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.clickable { onNavigate("gundu_ata") }
        ) {
            Image(
                painter = painterResource(id = R.drawable.app_logo),
                contentDescription = "App Logo",
                modifier = Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(8.dp))
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = "Gundu Ata",
                color = TextWhite,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold
            )
        }
        
        if (isLoggedIn) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Balance Pill
                Surface(
                    color = SurfaceColor,
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier
                        .padding(end = 12.dp)
                        .clickable { onWalletClick() }
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("₹", color = PrimaryYellow, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(balance, color = TextWhite, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(8.dp))
                        Icon(
                            Icons.Default.AddBox,
                            contentDescription = null,
                            tint = PrimaryYellow,
                            modifier = Modifier.size(20.dp)
                        )
                    }
                }
            }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(
                    onClick = { onNavigate("login") }
                ) {
                    Text(
                        text = "Login",
                        color = TextWhite,
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp
                    )
                }
                Spacer(modifier = Modifier.width(8.dp))
                Button(
                    onClick = { onNavigate("signup") },
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                    shape = RoundedCornerShape(20.dp),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    Text(
                        text = "Register",
                        color = BlackBackground,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
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
fun PromotionalBanners(onNavigate: (String) -> Unit) {
    val pageCount = 3
    val virtualCount = 1000 * pageCount
    val pagerState = rememberPagerState(
        initialPage = virtualCount / 2,
        pageCount = { virtualCount }
    )

    // Prevent multiple rapid clicks
    var lastClickTime by remember { mutableStateOf(0L) }
    val clickCooldown = 1000L // 1 second cooldown

    fun handleBannerClick(route: String) {
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
                1 -> BannerData("GET LUCKY DRAW", "WITH BANK TRANSFER", "SPIN", listOf(Color(0xFF4A148C), Color(0xFF880E4F)), { handleBannerClick("lucky_draw") })
                else -> BannerData("DAILY REWARD", "SPIN THE WHEEL FOR BONUS!", "SPIN NOW", listOf(Color(0xFFF9A825), Color(0xFFF57F17)), { handleBannerClick("lucky_wheel") })
            }

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .clip(RoundedCornerShape(16.dp))
                    .background(Brush.horizontalGradient(banner.gradient)),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(banner.title, color = PrimaryYellow, fontWeight = FontWeight.ExtraBold, fontSize = 24.sp)
                    Text(banner.subtitle, color = TextWhite, fontWeight = FontWeight.Bold)
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
        
        // Indicators
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
fun HotGamesGrid(onGameClick: (String) -> Unit) {
    // Grid for hot games - Only Gundu Ata
    val games = listOf(
        GameItem("Gundu Ata", "gundu_ata", Color(0xFF1565C0))
    )
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.Center
    ) {
        games.forEach { game ->
            GameCard(game, Modifier.fillMaxWidth(0.5f), onGameClick)
        }
    }
}

data class GameItem(val name: String, val id: String, val color: Color)

@Composable
fun GameCard(game: GameItem, modifier: Modifier, onGameClick: (String) -> Unit) {
    Column(
        modifier = modifier.clickable { onGameClick(game.id) },
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
                VideoPlayer(
                    videoResId = R.raw.gundu_ata_video,
                    modifier = Modifier.fillMaxSize()
                )
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

@Composable
fun VideoPlayer(videoResId: Int, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().apply {
            val uri = Uri.parse("android.resource://${context.packageName}/$videoResId")
            setMediaItem(MediaItem.fromUri(uri))
            repeatMode = Player.REPEAT_MODE_ALL
            playWhenReady = true
            prepare()
        }
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> {
                    exoPlayer.playWhenReady = true
                }
                Lifecycle.Event.ON_PAUSE -> {
                    exoPlayer.playWhenReady = false
                }
                Lifecycle.Event.ON_DESTROY -> {
                    exoPlayer.release()
                }
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
fun RelatedGamesList() {
    LazyRow(
        modifier = Modifier.padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        items(3) {
            Box(
                modifier = Modifier
                    .width(300.dp)
                    .height(150.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(SurfaceColor)
            )
        }
    }
}

@Composable
fun HomeBottomNavigation(currentRoute: String, onNavigate: (String) -> Unit) {
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
                onClick = { onNavigate(item.route) },
                icon = { Icon(item.icon, contentDescription = null) },
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

data class BottomNavItem(val name: String, val route: String, val icon: ImageVector)
