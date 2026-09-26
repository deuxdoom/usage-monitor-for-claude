// Glass Layer
// ===========
//
// The native layer under the popup's page for the glass material. It asks the
// Windows compositor for what lies behind the window (a backdrop brush), blurs
// it, lifts its saturation and caps every pixel's brightness, and draws the
// result under the WebView2 page. The compositor does all of it on the GPU:
// no screen pixel ever reaches this process, so nothing is copied, stored or
// sent, and the glass follows whatever moves behind the window frame by frame.
//
// window_backdrop.py loads the compiled library (build.py compiles this file
// with the .NET Framework compiler every Windows ships) and owns every value
// drawn here: blur, saturation and the brightness cap arrive as arguments.
// Every call must run on the popup's WinForms UI thread.

using System;
using System.Numerics;
using System.Runtime.InteropServices;
using Windows.Graphics.Effects;
using Windows.UI.Composition;
using Windows.UI.Composition.Desktop;

namespace AIAgentsUsageMonitor {

public static class GlassLayer {
    static IntPtr dispatcherQueue;
    static Compositor compositor;
    static DesktopWindowTarget target;
    static ContainerVisual root;
    static SpriteVisual visual;
    // Held so they can be released: the compositor keeps GPU resources for each until it is disposed.
    static CompositionEffectFactory factory;
    static CompositionBackdropBrush backdrop;
    static CompositionEffectBrush brush;
    static float saturation, brightnessCap;

    // Put the glass under the page of window hwnd. Returns "" on success, else the error.
    public static string Attach(IntPtr hwnd, float blur, float saturationFactor, float cap) {
        try {
            Detach();
            if (dispatcherQueue == IntPtr.Zero) {
                var options = new DispatcherQueueOptions { size = Marshal.SizeOf(typeof(DispatcherQueueOptions)), threadType = 2, apartmentType = 2 };
                Marshal.ThrowExceptionForHR(CreateDispatcherQueueController(options, out dispatcherQueue));
            }
            if (compositor == null) compositor = new Compositor();

            object created;
            // topmost: false keeps the layer under the window's own content, the WebView2 page.
            ((ICompositorDesktopInterop)(object)compositor).CreateDesktopWindowTarget(hwnd, false, out created);
            target = (DesktopWindowTarget)created;
            root = compositor.CreateContainerVisual();
            // Larger than any window; the compositor clips it to the window.
            root.Size = new Vector2(16384, 16384);
            target.Root = root;
            visual = compositor.CreateSpriteVisual();
            visual.RelativeSizeAdjustment = Vector2.One;
            root.Children.InsertAtTop(visual);

            saturation = saturationFactor;
            brightnessCap = cap;
            // A layer without its effect would show the desktop uncapped under the page.
            var failure = SetBlur(blur);
            if (failure != "") Detach();
            return failure;
        } catch (Exception error) {
            Detach();
            return error.ToString();
        }
    }

    // Blur is in physical pixels, so it is set again when the window moves to a monitor of another scale.
    public static string SetBlur(float blur) {
        try {
            if (visual == null) return "not attached";

            // Cap first, then saturate and blur once. Every pixel is at or below the cap before the blur
            // averages them, so the result is too, and saturation keeps each pixel's luma - one blur pass
            // instead of two, which is what the compositor has to redo on every frame while the window moves.
            // The gain min(1, cap / luma) leaves darker pixels as they are. The compositor accepts only
            // tree-shaped effect graphs, so the gain reads the backdrop through its own parameter node.
            IGraphicsEffectSource gain = new CompositionEffectSourceParameter("backdrop");
            gain = new Effect(ColorMatrix, new object[] { LumaToGray, StraightAlpha, true }, gain);
            gain = new Effect(GammaTransfer, new object[] {
                brightnessCap, -1f, 0f, false, brightnessCap, -1f, 0f, false, brightnessCap, -1f, 0f, false, 1f, 1f, 0f, true, true }, gain);

            IGraphicsEffectSource shown = new Effect(ArithmeticComposite, new object[] { new float[] { 1, 0, 0, 0 }, true },
                new CompositionEffectSourceParameter("backdrop"), gain);
            shown = new Effect(Saturation, new object[] { saturation }, shown);
            var capped = new Effect(GaussianBlur, new object[] { blur, BalancedOptimization, HardBorder }, shown);
            var newFactory = compositor.CreateEffectFactory(capped);
            var newBackdrop = compositor.CreateBackdropBrush();
            var newBrush = newFactory.CreateBrush();
            newBrush.SetSourceParameter("backdrop", newBackdrop);
            visual.Brush = newBrush;
            ReleaseBrush();
            factory = newFactory;
            backdrop = newBackdrop;
            brush = newBrush;
            return "";
        } catch (Exception error) {
            return error.ToString();
        }
    }

    public static void Detach() {
        if (visual != null) visual.Brush = null;
        ReleaseBrush();
        if (visual != null) visual.Dispose();
        if (root != null) root.Dispose();
        if (target != null) target.Dispose();
        visual = null;
        root = null;
        target = null;
    }

    static void ReleaseBrush() {
        if (brush != null) brush.Dispose();
        if (backdrop != null) backdrop.Dispose();
        if (factory != null) factory.Dispose();
        brush = null;
        backdrop = null;
        factory = null;
    }

    // Direct2D effect IDs and property values, as documented for each effect.
    static readonly Guid GaussianBlur = new Guid("1FEB6D69-2FE6-4AC9-8C58-1D7F93E7A6A5");
    static readonly Guid Saturation = new Guid("5CB2D9CF-327D-459F-A0CE-40C0B2086BF7");
    static readonly Guid ColorMatrix = new Guid("921F03D6-641C-47DF-852D-B4BB6153AE11");
    static readonly Guid GammaTransfer = new Guid("409444C4-C419-41A0-B0C1-8CD0C0A18E42");
    static readonly Guid ArithmeticComposite = new Guid("FC151437-049A-4784-A24A-F1C4DAF20987");
    const uint BalancedOptimization = 1, HardBorder = 1, StraightAlpha = 2;
    // Rec. 709 luma into all three color channels, opaque alpha.
    static readonly float[] LumaToGray = {
        .2126f, .2126f, .2126f, 0,
        .7152f, .7152f, .7152f, 0,
        .0722f, .0722f, .0722f, 0,
        0, 0, 0, 0,
        0, 0, 0, 1,
    };

    [StructLayout(LayoutKind.Sequential)]
    struct DispatcherQueueOptions { public int size, threadType, apartmentType; }

    [DllImport("CoreMessaging.dll")]
    static extern int CreateDispatcherQueueController(DispatcherQueueOptions options, out IntPtr controller);
}

[ComImport, Guid("29E691FA-4567-4DCA-B319-D0F207EB6807"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface ICompositorDesktopInterop {
    void CreateDesktopWindowTarget(IntPtr hwnd, [MarshalAs(UnmanagedType.Bool)] bool topmost, [MarshalAs(UnmanagedType.IInspectable)] out object target);
}

[ComImport, Guid("2FC57384-A068-44D7-A331-30982FCF7177"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IGraphicsEffectD2D1Interop {
    void GetEffectId(out Guid id);
    void GetNamedPropertyMapping([MarshalAs(UnmanagedType.LPWStr)] string name, out uint index, out uint mapping);
    void GetPropertyCount(out uint count);
    void GetProperty(uint index, out IntPtr value);
    void GetSource(uint index, out IGraphicsEffectSource source);
    void GetSourceCount(out uint count);
}

// One Direct2D effect in the graph: its ID, its properties by index and its inputs.
[ComVisible(true), ClassInterface(ClassInterfaceType.None)]
public class Effect : IGraphicsEffect, IGraphicsEffectSource, IGraphicsEffectD2D1Interop {
    readonly Guid id;
    readonly object[] properties;
    readonly IGraphicsEffectSource[] sources;
    static int created;

    public Effect(Guid id, object[] properties, params IGraphicsEffectSource[] sources) {
        this.id = id;
        this.properties = properties;
        this.sources = sources;
        Name = "effect" + (++created);
    }

    public string Name { get; set; }
    public void GetEffectId(out Guid effectId) { effectId = id; }
    // No property is animated, so none is mapped by name.
    public void GetNamedPropertyMapping(string name, out uint index, out uint mapping) { index = 0; mapping = 0; }
    public void GetPropertyCount(out uint count) { count = (uint)properties.Length; }
    public void GetProperty(uint index, out IntPtr value) { value = PropertyValues.Box(properties[index]); }
    public void GetSource(uint index, out IGraphicsEffectSource source) { source = sources[index]; }
    public void GetSourceCount(out uint count) { count = (uint)sources.Length; }
}

// Boxes a property as the native IPropertyValue the compositor reads, through the
// Windows.Foundation.PropertyValue statics. The managed boxing that .NET Framework
// offers is not accepted by CreateEffectFactory, so the statics are called by vtable slot.
static class PropertyValues {
    const int CreateUInt32 = 11, CreateSingle = 14, CreateBoolean = 17, CreateSingleArray = 33;
    static IntPtr statics;

    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int SingleBox(IntPtr self, float value, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int UIntBox(IntPtr self, uint value, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int BoolBox(IntPtr self, byte value, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int ArrayBox(IntPtr self, uint length, float[] values, out IntPtr result);

    public static IntPtr Box(object value) {
        IntPtr result;
        if (value is float) Marshal.ThrowExceptionForHR(Slot<SingleBox>(CreateSingle)(statics, (float)value, out result));
        else if (value is uint) Marshal.ThrowExceptionForHR(Slot<UIntBox>(CreateUInt32)(statics, (uint)value, out result));
        else if (value is bool) Marshal.ThrowExceptionForHR(Slot<BoolBox>(CreateBoolean)(statics, (byte)((bool)value ? 1 : 0), out result));
        else {
            var values = (float[])value;
            Marshal.ThrowExceptionForHR(Slot<ArrayBox>(CreateSingleArray)(statics, (uint)values.Length, values, out result));
        }
        return result;
    }

    static T Slot<T>(int slot) where T : class {
        if (statics == IntPtr.Zero) {
            IntPtr name;
            const string className = "Windows.Foundation.PropertyValue";
            Marshal.ThrowExceptionForHR(WindowsCreateString(className, className.Length, out name));
            try {
                var iid = new Guid("629BDBC8-D932-4FF4-96B9-8D96C5C1E858");
                Marshal.ThrowExceptionForHR(RoGetActivationFactory(name, ref iid, out statics));
            } finally {
                WindowsDeleteString(name);
            }
        }
        IntPtr function = Marshal.ReadIntPtr(Marshal.ReadIntPtr(statics), slot * IntPtr.Size);
        return (T)(object)Marshal.GetDelegateForFunctionPointer(function, typeof(T));
    }

    [DllImport("combase.dll", CharSet = CharSet.Unicode)] static extern int WindowsCreateString(string text, int length, out IntPtr value);
    [DllImport("combase.dll")] static extern int WindowsDeleteString(IntPtr value);
    [DllImport("combase.dll")] static extern int RoGetActivationFactory(IntPtr name, ref Guid iid, out IntPtr factory);
}

}
