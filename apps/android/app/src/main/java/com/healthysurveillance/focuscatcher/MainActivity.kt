package com.healthysurveillance.focuscatcher

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                FocusCatcherCompanion()
            }
        }
    }
}

@Composable
private fun FocusCatcherCompanion() {
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = Color(0xFFF6EFE5),
    ) {
        Column(
            modifier =
                Modifier
                    .fillMaxSize()
                    .background(
                        brush =
                            Brush.verticalGradient(
                                colors =
                                    listOf(
                                        Color(0xFFF6EFE5),
                                        Color(0xFFEAF4FB),
                                    ),
                            ),
                    )
                    .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "Paired Focus Catcher",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = "Android companion scaffold for the later paired-camera track. Lightweight CV and pairing transport will live here.",
                style = MaterialTheme.typography.bodyLarge,
                color = Color(0xFF4F5A6D),
            )

            Card(
                shape = RoundedCornerShape(24.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = 0.72f)),
            ) {
                Column(
                    modifier =
                        Modifier
                            .fillMaxWidth()
                            .padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text("Pairing status", style = MaterialTheme.typography.titleLarge)
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        StatusPill(label = "Local-only")
                        StatusPill(label = "Laptop paired")
                        StatusPill(label = "Cue sync ready")
                    }
                    Text("Token: FC-LOCAL-PAIR-001", color = Color(0xFF4F5A6D))
                    Button(onClick = {}) {
                        Text("Start camera capture")
                    }
                }
            }

            Card(
                shape = RoundedCornerShape(24.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = 0.72f)),
            ) {
                Column(
                    modifier =
                        Modifier
                            .fillMaxWidth()
                            .padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Text("Tracked items", style = MaterialTheme.typography.titleLarge)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        listOf("phone", "notebook", "calculator").forEach { item ->
                            StatusPill(label = item)
                        }
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "The laptop remains the heavy local inference host in the hybrid paired mode. This app becomes the lightweight camera-side collector.",
                        color = Color(0xFF4F5A6D),
                    )
                }
            }

            Box(
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .background(
                            color = Color.White.copy(alpha = 0.58f),
                            shape = RoundedCornerShape(28.dp),
                        ),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(
                        modifier =
                            Modifier
                                .size(160.dp)
                                .background(
                                    brush =
                                        Brush.radialGradient(
                                            colors = listOf(Color(0xFFD6F4FF), Color(0xFF6CAFD5), Color(0xFF335A70)),
                                        ),
                                    shape = RoundedCornerShape(80.dp),
                                ),
                    )
                    Spacer(modifier = Modifier.height(14.dp))
                    Text("Future live camera preview", style = MaterialTheme.typography.titleMedium)
                }
            }
        }
    }
}

@Composable
private fun StatusPill(label: String) {
    Box(
        modifier =
            Modifier
                .background(
                    color = Color(0x14000000),
                    shape = RoundedCornerShape(999.dp),
                )
                .padding(horizontal = 14.dp, vertical = 9.dp),
    ) {
        Text(label)
    }
}
