package com.rewear.app.navigation

import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import androidx.navigation.NavHostController
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.FavoriteBorder

@Composable
fun BottomNavBar(navController: NavHostController) {
    val items = listOf(
        Screen.Home,
        Screen.Favorites,
        Screen.AddItem,
        Screen.Profile
    )
    val navBackStackEntry = navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry.value?.destination?.route

    NavigationBar {
        items.forEach { screen ->
            NavigationBarItem(
                selected = currentRoute == screen.route,
                onClick = {
                    if (currentRoute != screen.route) {
                        navController.navigate(screen.route) {
                            launchSingleTop = true
                        }
                    }
                },
                icon = {
                    val imageVector = when (screen) {
                        Screen.Home -> Icons.Filled.Home
                        Screen.Favorites -> Icons.Filled.FavoriteBorder
                        Screen.AddItem -> Icons.Filled.Add
                        Screen.Profile -> Icons.Filled.Person
                        else -> Icons.Filled.Home
                    }
                    Icon(imageVector = imageVector, contentDescription = screen.title)
                },
                label = { Text(screen.title) }
            )
        }
    }
}

