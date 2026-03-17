using System;
using System.Linq;
using System.Reflection;
using AForge.Video.DirectShow;
class P {
  static void Main(){
    var t = typeof(VideoCaptureDevice);
    foreach(var p in t.GetProperties(BindingFlags.Public|BindingFlags.Instance).OrderBy(x=>x.Name))
      Console.WriteLine("P " + p.Name + " : " + p.PropertyType.FullName);
    foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly).OrderBy(x=>x.Name))
      Console.WriteLine("M " + m.Name);
  }
}
