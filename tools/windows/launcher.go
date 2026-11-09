//go:build windows

// Build with GOOS=windows GOARCH=amd64 go build -ldflags="-s -w -H=windowsgui".
package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"unsafe"
)

func reportFailure(err error) {
	title, _ := syscall.UTF16PtrFromString("ResumeForge")
	message, _ := syscall.UTF16PtrFromString(fmt.Sprintf("ResumeForge could not start.\n\n%v\n\nReinstall the application or extract the complete portable ZIP.", err))
	syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(message)), uintptr(unsafe.Pointer(title)), 0x10)
}

func main() {
	executable, err := os.Executable()
	if err != nil {
		reportFailure(err)
		os.Exit(1)
	}
	runtime := filepath.Join(filepath.Dir(executable), "runtime")
	arguments := append([]string{"-B", "-m", "resumeforge.desktop"}, os.Args[1:]...)
	child := exec.Command(filepath.Join(runtime, "pythonw.exe"), arguments...)
	child.Dir = runtime
	if err := child.Run(); err != nil {
		reportFailure(err)
		os.Exit(1)
	}
}
