package com.sikwin.app.utils

import android.content.ContentResolver
import android.content.Context
import android.provider.ContactsContract
import androidx.core.content.ContextCompat
import android.Manifest
import android.content.pm.PackageManager

data class Contact(
    val name: String,
    val phoneNumber: String?,
    val email: String?
)

object ContactsHelper {
    
    fun hasContactsPermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.READ_CONTACTS
        ) == PackageManager.PERMISSION_GRANTED
    }
    
    fun getContacts(context: Context): List<Contact> {
        if (!hasContactsPermission(context)) {
            return emptyList()
        }
        
        val contacts = mutableListOf<Contact>()
        val contentResolver: ContentResolver = context.contentResolver
        
        val projection = arrayOf(
            ContactsContract.Contacts._ID,
            ContactsContract.Contacts.DISPLAY_NAME,
            ContactsContract.Contacts.HAS_PHONE_NUMBER
        )
        
        val cursor = contentResolver.query(
            ContactsContract.Contacts.CONTENT_URI,
            projection,
            null,
            null,
            ContactsContract.Contacts.DISPLAY_NAME + " ASC"
        )
        
        cursor?.use {
            val idColumn = it.getColumnIndex(ContactsContract.Contacts._ID)
            val nameColumn = it.getColumnIndex(ContactsContract.Contacts.DISPLAY_NAME)
            val hasPhoneColumn = it.getColumnIndex(ContactsContract.Contacts.HAS_PHONE_NUMBER)
            
            while (it.moveToNext()) {
                val id = it.getString(idColumn)
                val name = it.getString(nameColumn) ?: "Unknown"
                val hasPhone = it.getInt(hasPhoneColumn) > 0
                
                var phoneNumber: String? = null
                var email: String? = null
                
                // Get phone number
                if (hasPhone) {
                    val phoneCursor = contentResolver.query(
                        ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                        null,
                        ContactsContract.CommonDataKinds.Phone.CONTACT_ID + " = ?",
                        arrayOf(id),
                        null
                    )
                    phoneCursor?.use { pc ->
                        if (pc.moveToFirst()) {
                            val phoneColumn = pc.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)
                            phoneNumber = pc.getString(phoneColumn)
                        }
                    }
                }
                
                // Get email
                val emailCursor = contentResolver.query(
                    ContactsContract.CommonDataKinds.Email.CONTENT_URI,
                    null,
                    ContactsContract.CommonDataKinds.Email.CONTACT_ID + " = ?",
                    arrayOf(id),
                    null
                )
                emailCursor?.use { ec ->
                    if (ec.moveToFirst()) {
                        val emailColumn = ec.getColumnIndex(ContactsContract.CommonDataKinds.Email.DATA)
                        email = ec.getString(emailColumn)
                    }
                }
                
                contacts.add(Contact(name, phoneNumber, email))
            }
        }
        
        return contacts
    }
    
    fun getContactsAsJson(context: Context): String {
        val contacts = getContacts(context)
        val jsonArray = contacts.map { contact ->
            """
            {
                "name": "${contact.name.replace("\"", "\\\"")}",
                "phone": "${contact.phoneNumber ?: ""}",
                "email": "${contact.email ?: ""}"
            }
            """.trimIndent()
        }.joinToString(",", "[", "]")
        return jsonArray
    }
}
