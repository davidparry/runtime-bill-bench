package main

import (
	"crypto/rand"
	"fmt"
)

// generateUUID creates a version 4 UUID.
func generateUUID() string {
	uuid := make([]byte, 16)
	_, err := rand.Read(uuid)
	if err != nil {
		panic(fmt.Sprintf("failed to generate UUID: %v", err))
	}

	// Set version 4
	uuid[6] = (uuid[6] & 0x0f) | 0x40
	// Set variant 1
	uuid[8] = (uuid[8] & 0x3f) | 0x80

	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		uuid[0:4], uuid[4:6], uuid[6:8], uuid[8:10], uuid[10:16])
}
