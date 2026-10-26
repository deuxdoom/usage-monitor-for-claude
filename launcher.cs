// The public EXE owns a private runtime beside itself and waits for its
// PyInstaller child before removing it. No runtime files use the system TEMP.
using System;
using System.Collections;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class Launcher
{
    private const string RuntimePrefix = ".AIAgentsUsageMonitor-runtime-";
    private const string PayloadName = "AIAgentsUsageMonitor.Payload";
    private const string LeaseName = ".owner";
    private const string LeaseMarker = "AI Agents Usage Monitor runtime\n";

    [DllImport("kernel32.dll")]
    private static extern bool AttachConsole(uint processId);

    [DllImport("kernel32.dll")]
    private static extern bool AllocConsole();

    [STAThread]
    private static int Main(string[] args)
    {
        if (!AttachConsole(unchecked((uint)-1)) && Array.IndexOf(args, "--verbose") >= 0)
            AllocConsole();
        string executable = Assembly.GetExecutingAssembly().Location;
        string directory = Path.GetDirectoryName(executable);
        string runtime = null;
        FileStream lease = null;
        try
        {
            CleanAbandoned(directory, executable);
            runtime = Path.Combine(directory, RuntimePrefix + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(runtime);
            lease = new FileStream(Path.Combine(runtime, LeaseName), FileMode.CreateNew,
                                   FileAccess.ReadWrite, FileShare.Read);
            byte[] marker = Encoding.UTF8.GetBytes(LeaseMarker + executable);
            lease.Write(marker, 0, marker.Length);
            lease.Flush();
            string payload = Path.Combine(runtime, "AIAgentsUsageMonitor.exe");
            using (Stream embedded = Assembly.GetExecutingAssembly().GetManifestResourceStream(PayloadName))
            using (FileStream output = new FileStream(payload, FileMode.CreateNew, FileAccess.Write))
            {
                if (embedded == null)
                    throw new InvalidDataException("The embedded application is missing.");
                embedded.CopyTo(output);
            }
            string temporary = Path.Combine(runtime, "temp");
            Directory.CreateDirectory(temporary);
            ProcessStartInfo start = new ProcessStartInfo(payload, JoinArguments(args));
            start.UseShellExecute = false;
            start.WorkingDirectory = directory;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            foreach (string key in new ArrayList(start.EnvironmentVariables.Keys))
            {
                if (key.StartsWith("_PYI_", StringComparison.Ordinal) || key == "_MEIPASS2")
                    start.EnvironmentVariables.Remove(key);
            }
            start.EnvironmentVariables["PYINSTALLER_RESET_ENVIRONMENT"] = "1";
            foreach (string key in new string[] { "TEMP", "TMP" })
            {
                string original = "AI_AGENTS_USAGE_MONITOR_ORIGINAL_" + key;
                start.EnvironmentVariables[original] = Environment.GetEnvironmentVariable(original)
                    ?? Environment.GetEnvironmentVariable(key) ?? "";
            }
            start.EnvironmentVariables["TEMP"] = temporary;
            start.EnvironmentVariables["TMP"] = temporary;
            start.EnvironmentVariables["AI_AGENTS_USAGE_MONITOR_EXE"] = executable;
            start.EnvironmentVariables["AI_AGENTS_USAGE_MONITOR_PID"] = Process.GetCurrentProcess().Id.ToString();
            start.EnvironmentVariables["AI_AGENTS_USAGE_MONITOR_LEASE"] = Path.Combine(runtime, LeaseName);
            using (Process child = Process.Start(start))
            {
                if (child == null)
                    throw new IOException("The embedded application could not be started.");
                Thread output = new Thread(delegate() { ForwardOutput(child.StandardOutput.BaseStream, Console.OpenStandardOutput()); });
                Thread errors = new Thread(delegate() { ForwardOutput(child.StandardError.BaseStream, Console.OpenStandardError()); });
                output.Start();
                errors.Start();
                child.WaitForExit();
                output.Join();
                errors.Join();
                return child.ExitCode;
            }
        }
        catch (Exception error)
        {
            string message = "AI Agents Usage Monitor could not start.\n"
                + "Its folder must allow creating runtime files.\n\n" + error.Message;
            if (Array.IndexOf(args, "--self-test") < 0)
                MessageBox.Show(message, "AI Agents Usage Monitor", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Console.Error.WriteLine(message);
            return 1;
        }
        finally
        {
            if (lease != null)
                lease.Dispose();
            if (runtime != null)
                RemoveRuntime(directory, runtime);
        }
    }

    private static void ForwardOutput(Stream source, Stream destination)
    {
        try
        {
            source.CopyTo(destination);
            destination.Flush();
        }
        catch (IOException)
        {
            source.CopyTo(Stream.Null);
        }
    }

    private static string JoinArguments(string[] args)
    {
        StringBuilder result = new StringBuilder();
        foreach (string arg in args)
        {
            if (result.Length != 0)
                result.Append(' ');
            result.Append('"');
            int slashes = 0;
            foreach (char value in arg)
            {
                if (value == '\\')
                {
                    slashes++;
                    continue;
                }
                result.Append('\\', value == '"' ? slashes * 2 + 1 : slashes);
                result.Append(value);
                slashes = 0;
            }
            result.Append('\\', slashes * 2);
            result.Append('"');
        }
        return result.ToString();
    }

    private static void CleanAbandoned(string directory, string executable)
    {
        foreach (string candidate in Directory.GetDirectories(directory, RuntimePrefix + "*"))
        {
            try
            {
                if ((File.GetAttributes(candidate) & FileAttributes.ReparsePoint) != 0)
                    continue;
                string owner = Path.Combine(candidate, LeaseName);
                using (FileStream lease = new FileStream(owner, FileMode.Open, FileAccess.Read, FileShare.None))
                using (StreamReader reader = new StreamReader(lease))
                {
                    if (!String.Equals(reader.ReadToEnd(), LeaseMarker + executable, StringComparison.OrdinalIgnoreCase))
                        continue;
                }
                RemoveRuntime(directory, candidate);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }

    private static void RemoveRuntime(string directory, string runtime)
    {
        string parent = Path.GetDirectoryName(Path.GetFullPath(runtime));
        if (!String.Equals(parent, Path.GetFullPath(directory), StringComparison.OrdinalIgnoreCase)
            || !Path.GetFileName(runtime).StartsWith(RuntimePrefix, StringComparison.Ordinal))
            return;
        for (int attempt = 0; attempt < 30; attempt++)
        {
            try
            {
                if (Directory.Exists(runtime))
                {
                    // Retain ownership until every other file is gone, so a
                    // sharing violation can be retried on the next launch.
                    foreach (string entry in Directory.GetFileSystemEntries(runtime))
                    {
                        if (String.Equals(Path.GetFileName(entry), LeaseName, StringComparison.OrdinalIgnoreCase))
                            continue;
                        if (Directory.Exists(entry))
                            Directory.Delete(entry, true);
                        else
                            File.Delete(entry);
                    }
                    File.Delete(Path.Combine(runtime, LeaseName));
                    Directory.Delete(runtime);
                }
                return;
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            Thread.Sleep(100);
        }
    }
}
