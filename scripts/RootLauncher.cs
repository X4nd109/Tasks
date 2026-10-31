using System;
using System.Diagnostics;
using System.IO;

class Program {
    static int Main(string[] args) {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        string targetExe = Path.Combine(baseDir, "dist", "Tasks", "Tasks.exe");
        if (!File.Exists(targetExe)) {
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine("[!] dist\\Tasks\\Tasks.exe nicht gefunden. Bitte fuehre zuerst build.bat aus.");
            Console.ResetColor();
            return 1;
        }

        string arguments = "";
        if (args != null && args.Length > 0) {
            var escapedArgs = new string[args.Length];
            for (int i = 0; i < args.Length; i++) {
                string arg = args[i];
                if (arg.Contains(" ") || arg.Contains("\"")) {
                    escapedArgs[i] = "\"" + arg.Replace("\"", "\\\"") + "\"";
                } else {
                    escapedArgs[i] = arg;
                }
            }
            arguments = string.Join(" ", escapedArgs);
        }

        var psi = new ProcessStartInfo {
            FileName = targetExe,
            Arguments = arguments,
            UseShellExecute = false,
            WorkingDirectory = baseDir
        };

        try {
            var proc = Process.Start(psi);
            proc.WaitForExit();
            return proc.ExitCode;
        } catch (Exception ex) {
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine("[!] Fehler beim Starten von Tasks: " + ex.Message);
            Console.ResetColor();
            return 1;
        }
    }
}
