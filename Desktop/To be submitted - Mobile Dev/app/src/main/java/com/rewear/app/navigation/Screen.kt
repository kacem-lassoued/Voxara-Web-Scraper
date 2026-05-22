package com.rewear.app.navigation

sealed class Screen(val route: String, val title: String) {
    object Home : Screen("home", "Home")
    object Favorites : Screen("favorites", "Favorites")
    object AddItem : Screen("add_item", "Add Item")
    object Profile : Screen("profile", "Profile")
    object ItemDetail : Screen("item_detail", "Item Detail")
}

