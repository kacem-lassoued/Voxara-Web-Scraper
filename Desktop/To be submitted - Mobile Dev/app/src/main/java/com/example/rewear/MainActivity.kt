package com.rewear.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.rewear.app.ui.theme.RewearTheme
import com.rewear.app.navigation.ReWearNavHost

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            RewearTheme {
                ReWearNavHost()
            }
        }
    }
}
