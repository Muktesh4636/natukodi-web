package com.sikwin.app.utils

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat

/**
 * Example Composable showing how to request contacts permission and access contacts
 * 
 * Usage in your screen:
 * 
 * @Composable
 * fun MyScreen() {
 *     val context = LocalContext.current
 *     var contacts by remember { mutableStateOf<List<Contact>>(emptyList()) }
 *     
 *     val contactsPermissionLauncher = rememberLauncherForActivityResult(
 *         contract = ActivityResultContracts.RequestPermission()
 *     ) { isGranted: Boolean ->
 *         if (isGranted) {
 *             contacts = ContactsHelper.getContacts(context)
 *             // Now you can use contacts list
 *             // For example, send to backend:
 *             // viewModel.sendContacts(ContactsHelper.getContactsAsJson(context))
 *         }
 *     }
 *     
 *     LaunchedEffect(Unit) {
 *         if (ContactsHelper.hasContactsPermission(context)) {
 *             contacts = ContactsHelper.getContacts(context)
 *         } else {
 *             contactsPermissionLauncher.launch(Manifest.permission.READ_CONTACTS)
 *         }
 *     }
 *     
 *     // Display contacts or use them as needed
 *     Column {
 *         Text("Found ${contacts.size} contacts")
 *         contacts.forEach { contact ->
 *             Text("${contact.name}: ${contact.phoneNumber ?: "No phone"}")
 *         }
 *     }
 * }
 */

/**
 * Simple function to get contacts with permission check
 * Call this from any Composable screen
 */
@Composable
fun RequestContactsPermission(
    onContactsReceived: (List<Contact>) -> Unit
) {
    val context = LocalContext.current
    
    val contactsPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            val contacts = ContactsHelper.getContacts(context)
            onContactsReceived(contacts)
        }
    }
    
    LaunchedEffect(Unit) {
        if (ContactsHelper.hasContactsPermission(context)) {
            val contacts = ContactsHelper.getContacts(context)
            onContactsReceived(contacts)
        } else {
            contactsPermissionLauncher.launch(Manifest.permission.READ_CONTACTS)
        }
    }
}
